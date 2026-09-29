"""Bounded full-duplex OPIF TCP pump; exactly one caller owns send/receive."""
from collections import deque
import select
import socket
import struct
import time

from . import wire


class TCPClient(wire.OPIFClient):
    reliable_ordered = True

    def __init__(self, host: str, port: int, timeout: float = 5.0) -> None:
        self.socket = socket.create_connection((host, port), timeout=timeout)
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            self.socket.setblocking(False)
        except BaseException:
            self.socket.close()
            raise
        self.session = None
        self.pipeline_status = None
        self._control_counter = 0
        self._received = bytearray()
        self._decoder = wire.native_codec.Decoder() if wire.native_codec.AVAILABLE else None
        self._transmit = deque()
        self._queued_bytes = 0
        self._frame_deadlines = {}

    def set_frame_deadline(self, request_id, deadline):
        self._frame_deadlines[request_id] = deadline

    def release_frame_deadline(self, request_id):
        self._frame_deadlines.pop(request_id, None)

    def _send_encoded(self, message, indices=None) -> None:
        if hasattr(message.datagrams, 'tcp_bytes'):
            framed = message.datagrams.select(indices)
        else:
            selected = range(message.fragment_count) if indices is None else indices
            framed = b''.join(struct.pack('<I', len(message.datagrams[i])) + message.datagrams[i] for i in selected)
        if not framed:
            return
        if message.message_type == wire.MessageType.INFERENCE_REQUEST:
            deadline = self._frame_deadlines.get(message.request_id)
            if deadline is None:
                raise wire.ProtocolError('Inference transmission has no capture deadline')
        else:
            deadline = time.monotonic() + 1.0
        if deadline <= time.monotonic():
            raise TimeoutError('OPIF absolute send deadline exceeded')
        if self._queued_bytes + len(framed) > 4 * wire.MAXIMUM_LOGICAL_MESSAGE_BYTES or len(self._transmit) >= 128:
            raise wire.ProtocolError('OPIF bounded transmit queue is full')
        self._transmit.append([memoryview(framed), deadline])
        self._queued_bytes += len(framed)

    def _flush(self):
        budget = 65536
        while self._transmit and budget:
            data, deadline = self._transmit[0]
            if time.monotonic() >= deadline:
                raise TimeoutError('OPIF queued transmission exceeded capture deadline')
            try:
                count = self.socket.send(data[:budget])
            except (BlockingIOError, InterruptedError):
                return
            if count <= 0:
                raise ConnectionError('OPIF TCP closed while sending')
            self._queued_bytes -= count
            budget -= count
            if count == len(data):
                self._transmit.popleft()
            else:
                self._transmit[0][0] = data[count:]

    def _receive_ready(self):
        # Drain only already-ready data, bounded to 1 MiB per message attempt.
        # Preserve half-frame continuations, but spend only one transmit slice.
        # Draining all queued frames here would delay an already-ready result.
        flushed = False
        for _ in range(16):
            message = self._receive_until(time.monotonic())
            if message is not None:
                return message
            readable, writable, _ = select.select([self.socket], [self.socket] if self._transmit and not flushed else [], [], 0)
            if not readable and not writable:
                return None
            if readable:
                try:
                    chunk = self.socket.recv(65536)
                except (BlockingIOError, InterruptedError):
                    chunk = None
                if chunk == b'':
                    raise ConnectionError('OPIF TCP peer disconnected')
                if chunk is not None:
                    if self._decoder is not None:
                        self._decoder.feed(chunk)
                    else:
                        self._received.extend(chunk)
                        if len(self._received) > wire.MAXIMUM_LOGICAL_MESSAGE_BYTES:
                            raise wire.ProtocolError('OPIF receive buffer overflow')
            if writable:
                self._flush()
                flushed = True
        # Partial frames stay in the existing decoder/buffer for the next poll.
        return self._receive_until(time.monotonic())

    def _receive_until(self, deadline):
        while True:
            if self._decoder is not None:
                message = self._decoder.pop()
                if message is not None:
                    kind, session, request, crc, body = message
                    header = wire.Header(wire.MessageType(kind), 0, len(body), session, request, 0, 1, len(body), crc)
                    return header, body
            if len(self._received) >= 4:
                length = struct.unpack_from('<I', self._received)[0]
                if not wire.HEADER_BYTES <= length <= wire.MAXIMUM_DATAGRAM_BYTES:
                    raise wire.ProtocolError(f'invalid OPIF-over-TCP frame length {length}')
                if len(self._received) >= length + 4:
                    packet = bytes(self._received[4:length + 4])
                    del self._received[:length + 4]
                    return wire.Header.decode_datagram(packet)
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                return None
            if self._transmit:
                remaining = min(remaining, self._transmit[0][1] - now)
                if remaining <= 0:
                    raise TimeoutError('OPIF queued transmission deadline exceeded')
            readable, writable, _ = select.select([self.socket], [self.socket] if self._transmit else [], [], remaining)
            # Always drain a readable reply before spending another transmit slice.
            if readable:
                try:
                    chunk = self.socket.recv(65536)
                except (BlockingIOError, InterruptedError):
                    continue
                if not chunk:
                    raise ConnectionError('OPIF TCP peer disconnected')
                if self._decoder is not None:
                    self._decoder.feed(chunk)
                else:
                    self._received.extend(chunk)
                    if len(self._received) > wire.MAXIMUM_LOGICAL_MESSAGE_BYTES:
                        raise wire.ProtocolError('OPIF receive buffer overflow')
            if writable:
                self._flush()
            if not readable and not writable:
                return None
