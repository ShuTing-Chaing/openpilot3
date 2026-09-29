"""Authenticated CTM host framing. No vehicle publication or hardware mutation."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import socket
import select
import threading
import struct
import time

SCHEMA = 'ctm-host-auth-v1'
MODEL_SHA = 'e8d821733be15ebe9e27498bc27ad8bbbd741980ece37d77f377294010b8ff28'
HEADER = struct.Struct('<IIQ')
PIXELS = 393216
OUTPUT_FLOATS = 18452
MAX_PAYLOAD = 400000
HELLO, AUTH, READY, FRAME, RESULT, STOP = range(1, 7)

class HostError(RuntimeError):
  pass

def exact(sock, size, deadline):
  parts = bytearray()
  while len(parts) < size:
    left = deadline - time.monotonic()
    if left <= 0:
      raise HostError('Message deadline expired')
    if not select.select([sock],[],[],left)[0]:
      raise HostError("Message deadline expired")
    try:
      chunk = sock.recv(size-len(parts))
    except BlockingIOError:
      continue
    if not chunk:
      raise HostError('USB/host stream disconnected')
    parts.extend(chunk)
  return bytes(parts)

class HostLink:
  def __init__(self, sock, key, timeout=.25, client_role="benchmark", model_request=None):
    if len(key) != 32:
      raise HostError('Pairing key must contain 32 bytes')
    self.sock,self.key,self.timeout=sock,key,timeout
    self.sock.setblocking(False)
    self.write_lock=threading.Lock()
    self.client_role=client_role
    self.model_request=model_request
    self.expected_model_ref=None
    self.expected_model_sha=None
    self.nonce=b''
    self.seq=0
    self.sent={}

  def receive(self, timeout=None, signed=True):
    deadline=time.monotonic()+(self.timeout if timeout is None else timeout)
    header=exact(self.sock,HEADER.size,deadline)
    kind,size,seq=HEADER.unpack(header)
    if size>MAX_PAYLOAD:
      raise HostError('Host message exceeds payload limit')
    payload=exact(self.sock,size,deadline)
    if signed:
      mac=exact(self.sock,32,deadline)
      wanted=hmac.digest(self.key,self.nonce+header+payload,'sha256')
      if not hmac.compare_digest(mac,wanted):
        raise HostError('Host message authentication failed')
    return kind,seq,payload

  def send(self, kind, seq, payload=b''):
    if len(payload)>MAX_PAYLOAD:
      raise HostError('Payload exceeds limit')
    packet=HEADER.pack(kind,len(payload),seq)+payload
    packet+=hmac.digest(self.key,self.nonce+packet,"sha256")
    deadline=time.monotonic()+self.timeout
    with self.write_lock:
      view=memoryview(packet)
      while view:
        left=deadline-time.monotonic()
        if left<=0 or not select.select([],[self.sock],[],left)[1]:
          raise HostError("Send deadline expired")
        try:
          count=self.sock.send(view)
        except BlockingIOError:
          continue
        if count==0:raise HostError("Stream disconnected while sending")
        view=view[count:]

  def hello(self, timeout=30):
    kind,seq,payload=self.receive(timeout=timeout,signed=False)
    if kind!=HELLO or seq!=0:
      raise HostError('Expected host greeting')
    hello=json.loads(payload)
    expected={'schema':SCHEMA,'image_bytes':PIXELS,'scalar_floats':12,'output_floats':OUTPUT_FLOATS}
    if any(hello.get(k)!=v for k,v in expected.items()):
      raise HostError('Host protocol contract differs')
    auth={'schema':SCHEMA,'model_sha256':MODEL_SHA,'client_role':self.client_role}
    selecting=self.model_request is not None and hello.get('model_selection')=='by-ref-v1'
    if selecting:
      if self.client_role!='shadow':
        raise HostError('Model following is restricted to shadow comparison')
      ref=self.model_request['model_ref']
      available=next((m for m in hello.get('models',[]) if ref in m.get('refs',[])),None)
      digest=available.get('source_sha256','') if available else ''
      auth.update(model_ref=ref,model_name=self.model_request.get('model_name',ref),model_sha256=digest)
      self.expected_model_ref,self.expected_model_sha=ref,digest
    elif hello.get('model_sha256')!=MODEL_SHA or (self.model_request and self.model_request['model_ref']!='68b5f8e48602f4f88041efd7de6c99e97fda454e'):
      raise HostError('Host cannot provide the requested model')
    self.nonce=base64.b64decode(hello['nonce'],validate=True)
    if len(self.nonce)!=32:
      raise HostError('Invalid session nonce')
    self.send(AUTH,0,json.dumps(auth).encode())
    kind,seq,payload=self.receive(timeout=5)
    ready=json.loads(payload)
    if kind!=READY or seq!=0 or ready.get('ok') is not True:
      raise HostError('Host model not ready: '+str(ready.get('reason','authentication failed')))
    if selecting and (ready.get('model_ref')!=self.expected_model_ref or ready.get('model_sha256')!=self.expected_model_sha or ready.get('state_reset') is not True):
      raise HostError('Loaded host model identity or state reset differs')
    hello['selected_model']=ready
    return hello

  def submit(self, frame_id, camera_eof_ns, pixels, scalars):
    if len(pixels)!=PIXELS or len(scalars)!=48:
      raise HostError('Input shape differs')
    self.seq+=1
    self.sent[self.seq]=(frame_id,camera_eof_ns,time.monotonic())
    if len(self.sent)>4:
      raise HostError('More than four frames in flight')
    self.send(FRAME,self.seq,struct.pack('<QQ',frame_id,camera_eof_ns)+scalars+pixels)
    return self.seq

  def result(self, timeout=None):
    kind,seq,payload=self.receive(timeout)
    if kind!=RESULT or seq not in self.sent or seq!=min(self.sent) or len(payload)<20:
      raise HostError('Unexpected result frame or sequence')
    frame_id,eof,size=struct.unpack_from('<QQI',payload)
    fid,wanted_eof,started=self.sent.pop(seq)
    if fid!=frame_id or wanted_eof!=eof or size>4096 or len(payload)!=20+size+OUTPUT_FLOATS*4:
      raise HostError('Result identity or output shape differs')
    stats=json.loads(payload[20:20+size])
    if self.expected_model_ref is not None and (stats.get('model_ref')!=self.expected_model_ref or stats.get('model_sha256')!=self.expected_model_sha):
      raise HostError('Result belongs to a different model')
    stats['roundtrip_ms']=(time.monotonic()-started)*1000
    return seq,frame_id,eof,payload[20+size:],stats

  def close(self):
    try:
      self.send(STOP,0)
    except (OSError,HostError,ValueError):
      pass
    self.sock.close()

def tcp(host, port=5599, connect_timeout=5):
  sock=socket.create_connection((host,port),timeout=connect_timeout)
  sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
  return sock

def usbmux(udid, port=5599, path='/var/run/usbmuxd'):
  """Connect over physical USB via a local usbmuxd Unix socket, not an IP link."""
  import plistlib
  sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.settimeout(5);sock.connect(path)
  def request(message,tag):
    blob=plistlib.dumps({'ClientVersionString':'CTMHost','ProgName':'ctm-host','kLibUSBMuxVersion':3,**message})
    sock.sendall(struct.pack('<IIII',len(blob)+16,1,8,tag)+blob)
    deadline=time.monotonic()+5
    length,version,kind,reply_tag=struct.unpack('<IIII',exact(sock,16,deadline))
    if not 16<=length<=1048576 or (version,kind,reply_tag)!=(1,8,tag):raise HostError('Invalid usbmux response')
    return plistlib.loads(exact(sock,length-16,deadline))
  devices=request({'MessageType':'ListDevices'},1).get('DeviceList',[])
  matches=[d for d in devices if d.get('Properties',{}).get('SerialNumber','').replace('-','')==udid.replace('-','') and d.get('Properties',{}).get('ConnectionType')=='USB']
  if len(matches)!=1:sock.close();raise HostError('Exactly one matching physically USB-connected iPhone is required')
  response=request({'MessageType':'Connect','DeviceID':matches[0]['DeviceID'],'PortNumber':socket.htons(port)},2)
  if response.get('Number')!=0:sock.close();raise HostError(f'USBmux connect failed: {response.get("Number")}')
  return sock
