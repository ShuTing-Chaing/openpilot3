from __future__ import annotations
import queue
import threading
import time
from collections import deque
from .wire import HostError
from .priority import background_thread
from .faults import classify, HistoryResetRequired, TransientBackpressure

class AsyncSession:
  """Frame identities and their capture-time context stay paired until publication."""
  def __init__(self, link, maximum_age=.2, warming_up=False):
    if not .05 <= maximum_age <= .2:
      raise HostError('External result age must be between 50 and 200 ms')
    self.link,self.maximum_age=link,maximum_age
    self.warming_up=warming_up
    self.pending={}
    self.capacity=getattr(link, "queue_capacity", 3)
    if self.capacity not in (3, 4):raise HostError("Unsupported bounded transport capacity")
    self.results=queue.Queue(maxsize=self.capacity)
    self.outgoing=queue.Queue(maxsize=self.capacity)
    self.condition=threading.Condition()
    self.error=None
    self.stopped=False
    self.next_seq=1
    self.superseded_outputs=0
    self.soft_expiry = getattr(link, 'supports_soft_expiry', False)
    self.terminal_events = deque(maxlen=256)
    self.terminal_history = deque(maxlen=256)
    self.state_identity = None
    self.soft_reset_pending = False
    self.awaiting_soft_reset_epoch = False
    self.threads=[threading.Thread(target=self._send,daemon=True),threading.Thread(target=self._receive,daemon=True)]
    for thread in self.threads:thread.start()

  def _fail(self,error):
    with self.condition:
      if self.soft_expiry:error=classify(error)
      if self.error is None:self.error=error
      self.stopped=True
      self.condition.notify_all()
    try:self.link.sock.shutdown(2)
    except OSError:pass

  def check(self):
    with self.condition:
      if self.error is not None:
        if self.soft_expiry:raise self.error
        raise HostError(f'External inference stopped: {self.error}') from self.error
      if self.stopped:raise HostError('External session is stopped')
      now=time.monotonic()
      if not self.soft_expiry and any(now-item[0]>(1.0 if self.warming_up else self.maximum_age) for item in self.pending.values()):
        raise HostError('External result exceeded its publication deadline')

  def submit(self, frame_id,eof,pixels,scalars,context):
    self.check()
    reset_temporal = False
    with self.condition:
      if self.soft_reset_pending:
        # Let every old request complete before the client-side temporal reset
        # bit is sent. This keeps one TCP session alive through backpressure.
        if self.pending or not self.outgoing.empty():
          raise TransientBackpressure('External model is draining for a soft history reset')
        self.soft_reset_pending = False
        self.awaiting_soft_reset_epoch = True
        reset_temporal = True
      elif len(self.pending)>=self.capacity or self.outgoing.full():
        if self.soft_expiry:
          self.soft_reset_pending = True
          raise TransientBackpressure(f'External model has {self.capacity} outstanding frames')
        raise HostError('External result exceeded the local admission window')
      seq=self.next_seq;self.next_seq+=1
      self.pending[seq]=(time.monotonic(),context,int(frame_id),int(eof))
      try:
        item=(seq,frame_id,eof,pixels,scalars,reset_temporal) if self.soft_expiry else (seq,frame_id,eof,pixels,scalars)
        self.outgoing.put_nowait(item)
      except queue.Full as error:
        self.pending.pop(seq,None)
        self.next_seq -= 1
        if self.soft_expiry:
          self.soft_reset_pending = True
          raise TransientBackpressure('External send queue is full') from error
        raise HostError('External send queue is full') from error

  def poll(self,timeout=0):
    self.check()
    # A completed old request must be consumed before deciding whether a later
    # result is useful. Expiration concerns publication, not model execution.
    for _ in range(self.capacity):
      try:seq,fid,eof,output,stats=self.results.get(timeout=timeout)
      except queue.Empty:return None
      timeout=0
      with self.condition:
        if seq not in self.pending or seq!=min(self.pending):raise HostError('Publication sequence mismatch')
        started,context,expected_fid,expected_eof=self.pending.pop(seq)
      if (fid,eof)!=(expected_fid,expected_eof):raise HostError('Publication capture identity mismatch')
      age=time.monotonic()-started
      if not self.soft_expiry:
        if age>(1.0 if self.warming_up else self.maximum_age):raise HostError('Completed output is too old to publish')
        # Legacy CTM users never subscribed to these new diagnostics. Keep
        # those events bounded without changing their publication contract.
        self.terminal_events.append({'seq':seq,'request_id':seq,'frame_id':fid,'eof_ns':eof,'context':context,
                                     'opif_session_id':None,'state_epoch':None,'terminal':'executed',
                                     'identity_source':'legacy_connection','received_age_seconds':None})
        return output,context,age,stats
      observed = time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time,'CLOCK_BOOTTIME') else time.monotonic()
      source_age=observed-eof/1e9
      if source_age<0:raise HostError('Completed output capture is in the future')
      identity=(stats.get('opif_session_id'),stats.get('state_epoch'))
      if any(type(value) is not int or value<=0 for value in identity):raise HostError('Missing OPIF state identity')
      if self.state_identity is None:self.state_identity=identity
      if self.state_identity is None:
        self.state_identity=identity
      elif identity!=self.state_identity:
        if not self.awaiting_soft_reset_epoch or stats.get('soft_reset') is not True:
          raise HostError('OPIF state epoch changed inside an active session')
        self.state_identity=identity
      if stats.get('soft_reset') is True:
        self.awaiting_soft_reset_epoch=False
      if stats.get('request_id')!=seq:raise HostError('OPIF request identity differs from session sequence')
      expired=source_age>=self.maximum_age or stats.get('terminal')=='expired'
      terminal='expired' if expired else 'executed'
      received_ns = stats.get('parent_validated_boottime_ns')
      received_age = (received_ns-eof)/1e9 if type(received_ns) is int else None
      event={'seq':seq,'request_id':seq,'frame_id':fid,'eof_ns':eof,'context':context,
             'opif_session_id':identity[0],'state_epoch':identity[1],
             'soft_reset':bool(stats.get('soft_reset',False)),
             'opif_state_epoch':identity[1],'opif_request_id':seq,
             'terminal':terminal,'received_age_seconds':received_age,'consumed_age_seconds':source_age}
      if len(self.terminal_events)>=256:raise HostError('Unconsumed OPIF terminal event queue is full')
      self.terminal_events.append(event)
      self.terminal_history.append({key:value for key,value in event.items() if key!='context'})
      if expired:continue
      return output,context,age,dict(stats,terminal=terminal,source_age_seconds=source_age)
    return None

  def drain_events(self):
    events=list(self.terminal_events)
    self.terminal_events.clear()
    return events

  def poll_latest(self,timeout=0):
    result=self.poll(timeout)
    if result is None:return None
    while True:
      newer=self.poll()
      if newer is None:return result
      self.superseded_outputs+=1
      result=newer

  def _send(self):
    background_thread()
    try:
      while not self.stopped:
        try:item=self.outgoing.get(timeout=.05)
        except queue.Empty:continue
        if len(item)==6:
          seq,fid,eof,pixels,scalars,reset_temporal=item
        else:
          seq,fid,eof,pixels,scalars=item
          reset_temporal=False
        if reset_temporal:
          actual=self.link.submit(fid,eof,pixels,scalars,reset_temporal=True)
        else:
          actual=self.link.submit(fid,eof,pixels,scalars)
        if actual!=seq:raise HostError('Sender sequence diverged')
        with self.condition:self.condition.notify_all()
    except Exception as error:self._fail(error)

  def _receive(self):
    background_thread()
    try:
      while True:
        with self.condition:
          self.condition.wait_for(lambda:self.stopped or bool(self.link.sent))
          if self.stopped:return
        value=self.link.result(timeout=1.0 if self.warming_up else self.maximum_age)
        if value is None:
          if self.soft_expiry:continue
          raise HostError('Transport returned no result without a polling contract')
        self.results.put_nowait(value)
    except Exception as error:self._fail(error)

  def close(self, *, wait=True):
    self._fail(HostError('External session closed'))
    if wait:
      for thread in self.threads:thread.join(timeout=.3)
    self.link.sock.close()
