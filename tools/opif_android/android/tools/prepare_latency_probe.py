"""Build an exact-source temporary measurement overlay; never edit production."""
import argparse
import hashlib
import json
from pathlib import Path


def replace(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f'Expected exactly one source boundary: {before!r}')
    return text.replace(before, after)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = args.output / 'openpilot/sunnypilot/modeld_v2'
    host = model / 'external_host'
    host.mkdir(parents=True, exist_ok=False)
    source_map = {}
    def write(name, changes, module_import='from . import latency_trace as trace\n'):
        original = (args.before / 'external_host' / name).read_text()
        text = original
        for old, new in changes:
            text = replace(text, old, new)
        # Preserve __future__ imports when present.
        if 'from __future__ import annotations\n' in text:
            text = text.replace('from __future__ import annotations\n', 'from __future__ import annotations\n' + module_import, 1)
        else:
            text = module_import + text
        target = host / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        compile(text, str(target), 'exec')
        source_map[name] = {'before': hashlib.sha256(original.encode()).hexdigest(), 'instrumented': hashlib.sha256(text.encode()).hexdigest()}

    write('opif/tcp_wire.py', [
        ('        self._frame_deadlines = {}', '        self._frame_deadlines = {}\n        self._trace_tx = {}'),
        ('        self._queued_bytes += len(framed)', "        self._queued_bytes += len(framed)\n        self._trace_tx[id(self._transmit[-1])] = (message.request_id, int(message.message_type))\n        trace.emit('SEND_QUEUED', message.request_id, int(message.message_type), len(framed), self._queued_bytes)"),
        ('                self._transmit.popleft()', "                rid, kind = self._trace_tx.pop(id(self._transmit[0]))\n                trace.emit('SEND_DONE', rid, kind, self._queued_bytes)\n                self._transmit.popleft()"),
        ('                    kind, session, request, crc, body = message', "                    kind, session, request, crc, body = message\n                    if kind == wire.MessageType.INFERENCE_RESULT:\n                        trace.emit('FULL', request, session, len(body))"),
        ('            readable, writable, _ = select.select([self.socket], [self.socket] if self._transmit else [], [], remaining)', "            trace.emit('SELECT_BEGIN', 0, max(0, int(remaining * 1e9)), self._queued_bytes)\n            readable, writable, _ = select.select([self.socket], [self.socket] if self._transmit else [], [], remaining)\n            trace.emit('SELECT_END', 0, bool(readable), bool(writable))"),
    ], 'from .. import latency_trace as trace\n')
    write('opif/transport.py', [
        ('    self.session = client._require_session()', "    self.session = client._require_session()\n    trace.emit('SESSION', 0, self.session.session_id)"),
        ('  def poll(self, wait=.001):\n    now = time.monotonic()', "  def poll(self, wait=.001):\n    trace.emit('POLL_BEGIN', self.next_publish, max(0, int(wait * 1e9)))\n    now = time.monotonic()"),
        ('      ready.append((item.frame, item.result))', "      trace.emit('POLL_RESULT', self.next_publish)\n      ready.append((item.frame, item.result))"),
        ('    return ready', "    trace.emit('POLL_END', self.next_publish, len(ready))\n    return ready"),
        ('        item.result = wire._parse_inference_result(body, self.session)', "        item.result = wire._parse_inference_result(body, self.session)\n        trace.emit('PARSED', rid, item.result.inference_microseconds, item.result.queue_microseconds)"),
    ], 'from .. import latency_trace as trace\n')
    write('opif_client.py', [
        ('    frame = Frame(bytes(pixels)', "    trace.emit('WIRE_SUBMIT', seq, frame_id, eof)\n    frame = Frame(bytes(pixels)"),
        ('  def _fail(self, error):\n', '  def _fail(self, error):\n    trace.error(error)\n'),
    ])
    write('opif_process.py', [
        ('    finally:\n      child.close()', '    finally:\n      child.close()\n    trace.bind(self.proc.pid)'),
        ('        send(self.conn, {\'type\': \'frame\'', "        trace.emit('IPC_SUBMIT', seq, frame_id, eof)\n        send(self.conn, {'type': 'frame'"),
        ('        return seq, fid, eof, raw, stats', "        trace.emit('PARENT_IPC', seq, fid, eof)\n        return seq, fid, eof, raw, stats"),
        ("        seq = link.submit(header['frame_id'], header['eof_ns'], data[48:], data[:48])", "        trace.emit('WORKER_TAKE', header['seq'], header['frame_id'], header['eof_ns'])\n        seq = link.submit(header['frame_id'], header['eof_ns'], data[48:], data[:48])"),
        ("        send(conn, {'type': 'result'", "        trace.emit('IPC_FORWARD', seq, fid, eof)\n        send(conn, {'type': 'result'"),
        ('  except Exception as error:\n    try:\n      send(conn', '  except Exception as error:\n    trace.error(error)\n    try:\n      send(conn'),
    ])
    write('session.py', [
        ('    self.results=queue.Queue(maxsize=self.capacity)', '    self.results=queue.Queue(maxsize=self.capacity)\n    trace.attach_queue(self.results)'),
        ('    try:self.outgoing.put_nowait((seq,frame_id,eof,pixels,scalars))', '    trace.capture(seq,context)\n    try:self.outgoing.put_nowait((seq,frame_id,eof,pixels,scalars))'),
        ('    return output,context,age,stats', "    trace.emit('MODEL_TAKE',seq,fid,eof)\n    return output,context,age,stats"),
        ('  def _fail(self,error):\n', '  def _fail(self,error):\n    trace.error(error)\n'),
    ])
    write('qnn_hotstandby.py', [
        ('    meta = context[\'meta_main\']\n    self.last_input_frame', "    meta = context['meta_main']\n    trace.emit('TICK', 0, meta.frame_id, meta.timestamp_eof, self.remote_started, self.phase == 'latched_local')\n    self.last_input_frame"),
        ('        local_output = self.local.run(', "        trace.emit('LOCAL_BEGIN', 0, meta.frame_id, meta.timestamp_eof)\n        local_output = self.local.run("),
        ('        self.local_runs += 1', "        trace.emit('LOCAL_END', 0, meta.frame_id, meta.timestamp_eof)\n        self.local_runs += 1"),
        ('          remote_context = self.remote.output_context\n          if not self._valid', "          remote_context = self.remote.output_context\n          trace.emit('CHECKED', trace.rid(remote_context), remote_context['meta_main'].frame_id, remote_context['meta_main'].timestamp_eof)\n          if not self._valid"),
        ("          samples = getattr(self.remote, 'completed_samples'", "          trace.emit('VALID', trace.rid(remote_context))\n          samples = getattr(self.remote, 'completed_samples'"),
        ('  def _latch(self, reason):\n', '  def _latch(self, reason):\n    trace.error(reason)\n'),
    ])
    (host / 'latency_trace.py').write_bytes(Path(__file__).with_name('latency_trace.py').read_bytes())
    (model / 'modeld.py').write_bytes((args.before / 'modeld.py').read_bytes())
    (model / 'modeld.py').chmod(0o755)
    (args.output / 'instrumentation-sha256.json').write_text(json.dumps(source_map, indent=2) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
