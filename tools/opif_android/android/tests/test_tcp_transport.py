"""Exercise the TCP adapter against actual stream sockets, including timeouts."""
from pathlib import Path
import socket
import struct
import sys
import time
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'script' / 'opif_overlay'))
from opif import wire
from opif.tcp_wire import TCPClient


class TCPTransportTest(unittest.TestCase):
    def setUp(self):
        self.client = TCPClient.__new__(TCPClient)
        self.client.socket, self.peer = socket.socketpair()
        self.client._received = bytearray()

    def tearDown(self):
        self.client.close()
        self.peer.close()

    def packet(self, request):
        return wire.encode_message(wire.MessageType.PING, 12, request, b'hello').datagrams[0]

    def test_timeout_preserves_split_prefix_and_body_then_drains_coalesced_frames(self):
        packet = self.packet(1)
        frame = struct.pack('<I', len(packet)) + packet
        self.peer.sendall(frame[:2])
        self.assertIsNone(self.client._receive_until(time.monotonic() + .005))
        self.peer.sendall(frame[2:10])
        self.assertIsNone(self.client._receive_until(time.monotonic() + .005))
        second = self.packet(2)
        self.peer.sendall(frame[10:] + struct.pack('<I', len(second)) + second)
        self.assertEqual(self.client._receive_until(time.monotonic() + .1)[0].request_id, 1)
        # Even an expired polling deadline drains a complete buffered frame.
        self.assertEqual(self.client._receive_until(0)[0].request_id, 2)

    def test_send_batches_fragments_and_honors_selected_indices(self):
        message = wire.encode_message(wire.MessageType.PING, 12, 3, b'x' * 4096)
        self.client.socket.settimeout(.000001)
        self.client._send_encoded(message, [0, 2])
        expected = b''.join(struct.pack('<I', len(message.datagrams[i])) + message.datagrams[i] for i in (0, 2))
        self.peer.settimeout(.1)
        received = bytearray()
        while len(received) < len(expected):
            received.extend(self.peer.recv(65536))
        self.assertEqual(received, expected)
        self.assertEqual(self.client.socket.gettimeout(), 2.0)

    def test_invalid_length_and_eof_raise(self):
        self.peer.sendall(struct.pack('<I', 0xffffffff))
        with self.assertRaises(wire.ProtocolError):
            self.client._receive_until(time.monotonic() + .1)
        self.client._received.clear()
        self.peer.close()
        with self.assertRaises(ConnectionError):
            self.client._receive_until(time.monotonic() + .1)

    def test_partial_send_failure_closes_unrecoverable_stream(self):
        self.client.socket.close()
        self.client.socket = Mock()
        self.client.socket.sendall.side_effect = socket.timeout('partial send')
        message = wire.encode_message(wire.MessageType.PING, 12, 3, b'hello')
        with self.assertRaises(socket.timeout):
            self.client._send_encoded(message)
        self.client.socket.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
