#!/usr/bin/env python3
"""OPIF/1 wire codec and session control, adapted from Apple's reference client.

The Pipeline in transport.py is the sole socket reader during inference.
Session helpers own the socket only before/after that loop. crcmod-plus's
existing C extension replaces the standard-library CRC when available.
"""

from __future__ import annotations

import ipaddress
import re
import secrets
import select
import socket
import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from ..faults import FatalModelFault, TransportUnavailable


MAGIC = b"OPIF"
VERSION = 1
HEADER_BYTES = 40
MAXIMUM_DATAGRAM_BYTES = 1_232
MAXIMUM_LOGICAL_MESSAGE_BYTES = 1_048_576
PACKED_FRAME_BYTES = 6 * 128 * 256
PAIRED_FILE_BYTES = 2 * PACKED_FRAME_BYTES
INFERENCE_PREFIX_BYTES = 32
RESULT_PREFIX_BYTES = 24
ANNOUNCEMENT_BODY_BYTES = 24
PIPELINE_STATUS_BODY_BYTES = 12

START_TIMEOUT_SECONDS = 60.0
PING_TIMEOUT_SECONDS = 2.0
INFERENCE_TIMEOUT_SECONDS = 30.0
STOP_TIMEOUT_SECONDS = 1.0
KEEPALIVE_INTERVAL_SECONDS = 1.0
RECOVERY_INTERVAL_SECONDS = 0.15

HEADER_STRUCT = struct.Struct("<4sBBHHHQQHHII")
START_PREFIX_STRUCT = struct.Struct("<BBBBHHHH")
INFERENCE_PREFIX_STRUCT = struct.Struct("<BBBBH2xffQII")
RESULT_PREFIX_STRUCT = struct.Struct("<BBBBIIIQ")
RETRANSMIT_QUERY_STRUCT = struct.Struct("<BBHII")
ANNOUNCEMENT_STRUCT = struct.Struct("<BBHHHHHIQ")
PIPELINE_STATUS_STRUCT = struct.Struct("<BBBBQ")

# This reference client is intentionally pinned to the source model ABIs
# bundled by this repository. Production modeld must keep an equivalent
# allow-list and refuse to parse raw output from an unknown source hash.
SUPPORTED_SOURCE_MODEL_SHA256 = {
    "659727c4d4839adc4992a254409a54259a8756a743f2d567bf5fdc6579f8009b",
    "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4",
    "baa30b01cc980a2e616bca5c94f64b64cccce5acfd2456c48bd29da274f4d78b",
}
ABI_PATTERN = re.compile(
    r"sha256:([0-9a-f]{64});op-supercombo-(2576|2580|18452)-f(\d+)-d(\d+)-s(\d+)-v1"
)
COMPACT_ABI_PATTERN = re.compile(
    r"sha256:(404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4);op-supercombo-(2068)-f(32)-d(33)-s(4)-v2"
)


class MessageType(IntEnum):
    START_SESSION = 0x01
    STOP_SESSION = 0x02
    PING = 0x03
    RETRANSMIT_QUERY = 0x04
    MISSING_FRAGMENTS = 0x05
    MESSAGE_ACCEPTED = 0x06
    DISCOVER = 0x07

    INFERENCE_REQUEST = 0x10

    SESSION_READY = 0x81
    SESSION_STOPPED = 0x82
    PONG = 0x83
    ANNOUNCE = 0x84
    PIPELINE_STATUS = 0x85
    INFERENCE_RESULT = 0x90
    ERROR = 0xFF


class InputLayout(IntEnum):
    CURRENT_PACKED_6 = 0
    PAIRED_PACKED_12 = 1

    @property
    def tensor_bytes(self) -> int:
        if self is InputLayout.CURRENT_PACKED_6:
            return 2 * PACKED_FRAME_BYTES
        return 4 * PACKED_FRAME_BYTES


class OutputEncoding(IntEnum):
    FLOAT32_LE = 0
    FLOAT16_LE = 1
    CONTROL_HEADS_FLOAT32_LE = 2

    @property
    def element_bytes(self) -> int:
        return 2 if self is OutputEncoding.FLOAT16_LE else 4


class ServerAvailability(IntEnum):
    AVAILABLE = 0
    ACTIVATING = 1
    ACTIVE = 2


class ProtocolError(FatalModelFault):
    """An OPIF peer sent a well-formed datagram with invalid semantics."""


class MessageCRCError(ProtocolError):
    """A complete logical message did not match its advertised CRC32C."""


def _make_crc32c_table() -> Tuple[int, ...]:
    table: List[int] = []
    for value in range(256):
        crc = value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
        table.append(crc & 0xFFFFFFFF)
    return tuple(table)


CRC32C_TABLE = _make_crc32c_table()


def crc32c(data: bytes) -> int:
    """Return Castagnoli CRC-32C using the same init/final XOR as Swift."""

    crc = 0xFFFFFFFF
    for byte in data:
        crc = CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return (~crc) & 0xFFFFFFFF


@dataclass(frozen=True)
class Header:
    message_type: MessageType
    flags: int
    payload_bytes: int
    session_id: int
    request_id: int
    fragment_index: int
    fragment_count: int
    message_bytes: int
    message_crc32c: int

    def encode(self) -> bytes:
        return HEADER_STRUCT.pack(
            MAGIC,
            VERSION,
            int(self.message_type),
            self.flags,
            HEADER_BYTES,
            self.payload_bytes,
            self.session_id,
            self.request_id,
            self.fragment_index,
            self.fragment_count,
            self.message_bytes,
            self.message_crc32c,
        )

    @classmethod
    def decode_datagram(cls, datagram: bytes) -> Tuple["Header", bytes]:
        if len(datagram) < HEADER_BYTES:
            raise ProtocolError(f"short UDP datagram ({len(datagram)} bytes)")
        (
            magic,
            version,
            raw_type,
            flags,
            header_bytes,
            payload_bytes,
            session_id,
            request_id,
            fragment_index,
            fragment_count,
            message_bytes,
            message_crc,
        ) = HEADER_STRUCT.unpack_from(datagram)
        if magic != MAGIC or version != VERSION or header_bytes != HEADER_BYTES:
            raise ProtocolError("not an OPIF/1 datagram with a 40-byte header")
        if flags != 0:
            raise ProtocolError(f"unsupported OPIF/1 header flags 0x{flags:04x}")
        try:
            message_type = MessageType(raw_type)
        except ValueError as error:
            raise ProtocolError(f"unknown OPIF message type 0x{raw_type:02x}") from error
        payload = datagram[HEADER_BYTES:]
        if payload_bytes != len(payload):
            raise ProtocolError(
                f"payload length mismatch: header={payload_bytes}, UDP={len(payload)}"
            )
        if fragment_count == 0 or fragment_index >= fragment_count:
            raise ProtocolError("invalid fragment index/count")
        if message_bytes > MAXIMUM_LOGICAL_MESSAGE_BYTES:
            raise ProtocolError(f"logical message is too large ({message_bytes} bytes)")
        return (
            cls(
                message_type=message_type,
                flags=flags,
                payload_bytes=payload_bytes,
                session_id=session_id,
                request_id=request_id,
                fragment_index=fragment_index,
                fragment_count=fragment_count,
                message_bytes=message_bytes,
                message_crc32c=message_crc,
            ),
            payload,
        )


@dataclass(frozen=True)
class EncodedMessage:
    message_type: MessageType
    session_id: int
    request_id: int
    body: bytes
    crc: int
    datagrams: Tuple[bytes, ...]

    @property
    def fragment_count(self) -> int:
        return len(self.datagrams)


def encode_message(
    message_type: MessageType,
    session_id: int,
    request_id: int,
    body: bytes,
    maximum_datagram_bytes: int = MAXIMUM_DATAGRAM_BYTES,
    flags: int = 0,
) -> EncodedMessage:
    if flags != 0:
        raise ValueError("OPIF/1 header flags must be zero")
    if not (HEADER_BYTES < maximum_datagram_bytes <= 65_507):
        raise ValueError(f"invalid maximum datagram size {maximum_datagram_bytes}")
    if len(body) > MAXIMUM_LOGICAL_MESSAGE_BYTES:
        raise ValueError(f"logical message is too large ({len(body)} bytes)")

    payload_limit = maximum_datagram_bytes - HEADER_BYTES
    fragment_count = max(1, (len(body) + payload_limit - 1) // payload_limit)
    if fragment_count > 0xFFFF:
        raise ValueError(f"too many fragments ({fragment_count})")
    if native_codec.AVAILABLE:
        packets = native_codec.NativePackets(message_type, session_id, request_id, body, maximum_datagram_bytes)
        return EncodedMessage(message_type, session_id, request_id, body, packets.crc, packets)
    checksum = crc32c(body)
    datagrams: List[bytes] = []
    for index in range(fragment_count):
        lower = min(len(body), index * payload_limit)
        upper = min(len(body), lower + payload_limit)
        payload = body[lower:upper]
        header = Header(
            message_type=message_type,
            flags=flags,
            payload_bytes=len(payload),
            session_id=session_id,
            request_id=request_id,
            fragment_index=index,
            fragment_count=fragment_count,
            message_bytes=len(body),
            message_crc32c=checksum,
        )
        datagrams.append(header.encode() + payload)
    return EncodedMessage(
        message_type=message_type,
        session_id=session_id,
        request_id=request_id,
        body=body,
        crc=checksum,
        datagrams=tuple(datagrams),
    )


@dataclass
class MessageAssembly:
    message_type: MessageType
    session_id: int
    request_id: int
    fragment_count: int
    message_bytes: int
    message_crc32c: int
    fragments: List[Optional[bytes]] = field(repr=False)

    @classmethod
    def from_header(cls, header: Header) -> "MessageAssembly":
        return cls(
            message_type=header.message_type,
            session_id=header.session_id,
            request_id=header.request_id,
            fragment_count=header.fragment_count,
            message_bytes=header.message_bytes,
            message_crc32c=header.message_crc32c,
            fragments=[None] * header.fragment_count,
        )

    def accepts(self, header: Header) -> bool:
        return (
            header.message_type == self.message_type
            and header.session_id == self.session_id
            and header.request_id == self.request_id
            and header.fragment_count == self.fragment_count
            and header.message_bytes == self.message_bytes
            and header.message_crc32c == self.message_crc32c
        )

    def add(self, header: Header, payload: bytes) -> bool:
        if not self.accepts(header):
            raise ProtocolError("inconsistent fragment metadata")
        previous = self.fragments[header.fragment_index]
        if previous is not None and previous != payload:
            raise ProtocolError("duplicate fragment has different contents")
        changed = previous is None
        self.fragments[header.fragment_index] = payload
        return changed

    def complete_body(self) -> Optional[bytes]:
        if any(fragment is None for fragment in self.fragments):
            return None
        body = b"".join(fragment for fragment in self.fragments if fragment is not None)
        if len(body) != self.message_bytes:
            raise ProtocolError(
                f"reassembled length mismatch: expected {self.message_bytes}, got {len(body)}"
            )
        actual_crc = crc32c(body)
        if actual_crc != self.message_crc32c:
            raise MessageCRCError(
                f"message CRC32C mismatch: expected {self.message_crc32c:08x}, "
                f"got {actual_crc:08x}"
            )
        return body

    def missing_bitmap(self) -> bytes:
        bitmap = bytearray((self.fragment_count + 7) // 8)
        for index, fragment in enumerate(self.fragments):
            if fragment is None:
                bitmap[index // 8] |= 1 << (index % 8)
        return bytes(bitmap)

    def reset_all(self) -> None:
        self.fragments = [None] * self.fragment_count


@dataclass(frozen=True)
class Session:
    session_id: int
    layout: InputLayout
    output_encoding: OutputEncoding
    maximum_datagram_bytes: int
    tensor_bytes: int
    output_elements: int
    lease_milliseconds: int
    feature_frames: int
    desire_history: int
    frame_skip: int
    maximum_in_flight: int
    model_name: str
    abi_identifier: str
    source_model_sha256: str


@dataclass(frozen=True)
class InferenceResult:
    raw_output: bytes
    encoding: OutputEncoding
    raw_output_layout: int
    inference_microseconds: int
    queue_microseconds: int
    server_timestamp_ns: int


    @property
    def values(self):
        code = "e" if self.encoding is OutputEncoding.FLOAT16_LE else "f"
        return struct.unpack(f"<{len(self.raw_output) // self.encoding.element_bytes}{code}", self.raw_output)


@dataclass(frozen=True)
class PipelineStatus:
    current_depth: int
    supported_maximum: int
    revision: int


@dataclass(frozen=True)
class DiscoveredServer:
    host: str
    port: int
    availability: ServerAvailability
    accepts_start: bool
    maximum_datagram_bytes: int
    minimum_datagram_bytes: int
    lease_milliseconds: int
    instance_id: int
    round_trip_milliseconds: float


def _parse_error(body: bytes) -> Tuple[int, int, str]:
    if len(body) < 12:
        raise ProtocolError("short ERROR body")
    code, text_bytes, expected_request_id = struct.unpack_from("<HHQ", body)
    if len(body) != 12 + text_bytes:
        raise ProtocolError("ERROR text length mismatch")
    try:
        message = body[12:].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProtocolError("ERROR text is not UTF-8") from error
    return code, expected_request_id, message


def _parse_pipeline_status(body: bytes) -> PipelineStatus:
    if len(body) != PIPELINE_STATUS_BODY_BYTES:
        raise ProtocolError(
            f"PIPELINE_STATUS body must be {PIPELINE_STATUS_BODY_BYTES} bytes"
        )
    schema, current_depth, supported_maximum, reserved, revision = (
        PIPELINE_STATUS_STRUCT.unpack(body)
    )
    if schema != 1 or reserved != 0:
        raise ProtocolError("unsupported PIPELINE_STATUS schema/reserved fields")
    if not 1 <= supported_maximum <= 4:
        raise ProtocolError(
            f"invalid PIPELINE_STATUS supported_maximum={supported_maximum}"
        )
    if not 1 <= current_depth <= supported_maximum:
        raise ProtocolError(
            "invalid PIPELINE_STATUS current_depth="
            f"{current_depth} for supported_maximum={supported_maximum}"
        )
    if revision == 0:
        raise ProtocolError("PIPELINE_STATUS revision zero is reserved")
    return PipelineStatus(
        current_depth=current_depth,
        supported_maximum=supported_maximum,
        revision=revision,
    )


def _select_pipeline_status(
    current: Optional[PipelineStatus], incoming: PipelineStatus
) -> PipelineStatus:
    if current is None or incoming.revision > current.revision:
        return incoming
    if incoming.revision < current.revision:
        return current
    if incoming != current:
        raise ProtocolError(
            f"conflicting PIPELINE_STATUS bodies for revision {incoming.revision}"
        )
    return current


def _parse_session_ready(
    body: bytes,
    session_id: int,
    requested_layout: InputLayout,
    requested_output: OutputEncoding,
) -> Session:
    if len(body) < 30:
        raise ProtocolError("short SESSION_READY body")
    status, raw_layout, compression, raw_output = struct.unpack_from("<BBBB", body)
    maximum_datagram, reserved = struct.unpack_from("<HH", body, 4)
    tensor_bytes, output_elements, lease_ms = struct.unpack_from("<III", body, 8)
    feature_frames, desire_history = struct.unpack_from("<HH", body, 20)
    frame_skip, maximum_in_flight = struct.unpack_from("<BB", body, 24)
    model_bytes, abi_bytes = struct.unpack_from("<HH", body, 26)
    if status != 0 or compression != 0 or reserved != 0:
        raise ProtocolError("unsupported SESSION_READY status/compression/reserved fields")
    if not 1 <= maximum_in_flight <= 4:
        raise ProtocolError(
            f"unsupported SESSION_READY maximum_in_flight={maximum_in_flight}"
        )
    try:
        layout = InputLayout(raw_layout)
        output = OutputEncoding(raw_output)
    except ValueError as error:
        raise ProtocolError("unknown SESSION_READY layout or output encoding") from error
    if layout != requested_layout or output != requested_output:
        raise ProtocolError(
            f"server negotiated unexpected layout/output ({layout.name}, {output.name})"
        )
    if tensor_bytes != layout.tensor_bytes:
        raise ProtocolError(
            f"server tensor size mismatch: expected {layout.tensor_bytes}, got {tensor_bytes}"
        )
    string_end = 30 + model_bytes + abi_bytes
    if string_end != len(body):
        raise ProtocolError("SESSION_READY string length mismatch")
    try:
        model_name = body[30 : 30 + model_bytes].decode("utf-8")
        abi_identifier = body[30 + model_bytes : string_end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProtocolError("SESSION_READY model/ABI name is not UTF-8") from error
    compact = output is OutputEncoding.CONTROL_HEADS_FLOAT32_LE
    abi_match = (COMPACT_ABI_PATTERN if compact else ABI_PATTERN).fullmatch(abi_identifier)
    if abi_match is None:
        raise ProtocolError(f"unsupported model ABI identifier {abi_identifier!r}")
    source_sha, abi_output, abi_features, abi_desires, abi_skip = abi_match.groups()
    if source_sha not in SUPPORTED_SOURCE_MODEL_SHA256:
        raise ProtocolError(f"source model SHA-256 is not allow-listed: {source_sha}")
    abi_shape = tuple(map(int, (abi_output, abi_features, abi_desires, abi_skip)))
    ready_shape = (output_elements, feature_frames, desire_history, frame_skip)
    if abi_shape != ready_shape:
        raise ProtocolError(
            f"ABI/profile mismatch: ABI={abi_shape}, SESSION_READY={ready_shape}"
        )
    if ready_shape not in {
        (2_576, 24, 25, 4),
        (18_452, 32, 33, 4),
        (2_580, 24, 25, 4),
        (2_580, 32, 33, 1),
        (2_068, 32, 33, 4),
    }:
        raise ProtocolError(f"unsupported model profile {ready_shape}")
    return Session(
        session_id=session_id,
        layout=layout,
        output_encoding=output,
        maximum_datagram_bytes=maximum_datagram,
        tensor_bytes=tensor_bytes,
        output_elements=output_elements,
        lease_milliseconds=lease_ms,
        feature_frames=feature_frames,
        desire_history=desire_history,
        frame_skip=frame_skip,
        maximum_in_flight=maximum_in_flight,
        model_name=model_name,
        abi_identifier=abi_identifier,
        source_model_sha256=source_sha,
    )


def _parse_inference_result(body: bytes, session: Session) -> InferenceResult:
    if len(body) < RESULT_PREFIX_BYTES:
        raise ProtocolError("short INFERENCE_RESULT body")
    (
        status,
        raw_encoding,
        raw_output_layout,
        reserved,
        element_count,
        inference_us,
        queue_us,
        server_timestamp_ns,
    ) = RESULT_PREFIX_STRUCT.unpack_from(body)
    if status != 0 or reserved != 0:
        raise ProtocolError("unsuccessful or reserved INFERENCE_RESULT prefix")
    try:
        encoding = OutputEncoding(raw_encoding)
    except ValueError as error:
        raise ProtocolError(f"unknown result encoding {raw_encoding}") from error
    if encoding != session.output_encoding:
        raise ProtocolError("result encoding differs from SESSION_READY")
    if element_count != session.output_elements:
        raise ProtocolError(
            f"result element count mismatch: ready={session.output_elements}, "
            f"result={element_count}"
        )
    expected_output_layout = 2 if encoding is OutputEncoding.CONTROL_HEADS_FLOAT32_LE else (1 if element_count == 2_580 else 0)
    if raw_output_layout != expected_output_layout:
        raise ProtocolError(
            f"raw output layout mismatch: expected {expected_output_layout}, "
            f"got {raw_output_layout}"
        )
    expected_bytes = RESULT_PREFIX_BYTES + element_count * encoding.element_bytes
    if len(body) != expected_bytes:
        raise ProtocolError(
            f"result byte count mismatch: expected {expected_bytes}, got {len(body)}"
        )
    return InferenceResult(
        raw_output=body[RESULT_PREFIX_BYTES:],
        encoding=encoding,
        raw_output_layout=raw_output_layout,
        inference_microseconds=inference_us,
        queue_microseconds=queue_us,
        server_timestamp_ns=server_timestamp_ns,
    )


def _indices_from_bitmap(bitmap: bytes, fragment_count: int) -> Iterable[int]:
    for index in range(fragment_count):
        if index // 8 < len(bitmap) and bitmap[index // 8] & (1 << (index % 8)):
            yield index


def _parse_announcement(
    header: Header,
    body: bytes,
    source_host: str,
    source_port: int,
    sent_at_by_request_id: Dict[int, float],
    received_at: float,
) -> DiscoveredServer:
    if (
        header.message_type is not MessageType.ANNOUNCE
        or header.session_id != 0
        or header.request_id not in sent_at_by_request_id
        or header.fragment_index != 0
        or header.fragment_count != 1
        or header.message_bytes != ANNOUNCEMENT_BODY_BYTES
        or len(body) != ANNOUNCEMENT_BODY_BYTES
    ):
        raise ProtocolError("ANNOUNCE correlation or fixed-size metadata mismatch")
    if crc32c(body) != header.message_crc32c:
        raise MessageCRCError("ANNOUNCE CRC32C mismatch")
    (
        schema,
        raw_availability,
        flags,
        service_port,
        maximum_datagram,
        minimum_datagram,
        reserved,
        lease_milliseconds,
        instance_id,
    ) = ANNOUNCEMENT_STRUCT.unpack(body)
    if schema != 1 or flags & ~0x0001 or reserved != 0:
        raise ProtocolError("unsupported ANNOUNCE schema, flags, or reserved field")
    try:
        availability = ServerAvailability(raw_availability)
    except ValueError as error:
        raise ProtocolError(f"unknown server availability {raw_availability}") from error
    accepts_start = bool(flags & 0x0001)
    if accepts_start != (availability is ServerAvailability.AVAILABLE):
        raise ProtocolError("ANNOUNCE availability and accepts-START flag disagree")
    if source_port != service_port or not (1 <= service_port <= 65_535):
        raise ProtocolError("ANNOUNCE source and advertised UDP ports disagree")
    if not (
        512 <= minimum_datagram <= maximum_datagram <= MAXIMUM_DATAGRAM_BYTES
    ):
        raise ProtocolError("ANNOUNCE datagram bounds are invalid")
    if not (1 <= lease_milliseconds <= 60_000) or instance_id == 0:
        raise ProtocolError("ANNOUNCE lease or instance ID is invalid")
    return DiscoveredServer(
        host=source_host,
        port=service_port,
        availability=availability,
        accepts_start=accepts_start,
        maximum_datagram_bytes=maximum_datagram,
        minimum_datagram_bytes=minimum_datagram,
        lease_milliseconds=lease_milliseconds,
        instance_id=instance_id,
        round_trip_milliseconds=max(
            0.0,
            (received_at - sent_at_by_request_id[header.request_id]) * 1_000.0,
        ),
    )


def discover_servers(
    subnet: str = "192.168.7.0/24",
    port: int = 5_555,
    timeout_seconds: float = 0.75,
    probe_rounds: int = 2,
) -> Tuple[DiscoveredServer, ...]:
    """Probe every IPv4 host concurrently without ICMP or Bonjour/mDNS.

    Each round queues one 40-byte directed-unicast DISCOVER datagram per usable
    address before waiting for replies. The iOS service only returns a fixed
    ANNOUNCE; discovery never sends START_SESSION and therefore cannot enter
    inference mode.
    """

    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as error:
        raise ValueError(f"invalid discovery subnet {subnet!r}") from error
    if network.version != 4:
        raise ValueError("automatic discovery currently requires an IPv4 subnet")
    if network.num_addresses > 4_096:
        raise ValueError("refusing to probe more than 4096 addresses")
    if not (1 <= port <= 65_535):
        raise ValueError("discovery port must be in 1..65535")
    if not (0.05 <= timeout_seconds <= 10.0):
        raise ValueError("discovery timeout must be in 0.05..10 seconds")
    if not (1 <= probe_rounds <= 3):
        raise ValueError("discovery probe rounds must be in 1..3")
    targets = tuple(str(address) for address in network.hosts())
    if not targets:
        raise ValueError("discovery subnet contains no usable addresses")

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
        udp_socket.bind(("0.0.0.0", 0))
        udp_socket.setblocking(False)
        started = time.monotonic()
        deadline = started + timeout_seconds
        # The second packet survives a single local Wi-Fi/ARP loss without
        # turning discovery into continuous background traffic.
        round_spacing = min(0.20, timeout_seconds / (probe_rounds + 1))
        round_deadlines = tuple(started + index * round_spacing for index in range(probe_rounds))
        next_round = 0
        sent_at_by_request_id: Dict[int, float] = {}
        discovered_by_instance: Dict[int, DiscoveredServer] = {}

        while time.monotonic() < deadline:
            now = time.monotonic()
            while next_round < probe_rounds and now >= round_deadlines[next_round]:
                request_id = secrets.randbits(64) or 1
                while request_id in sent_at_by_request_id:
                    request_id = secrets.randbits(64) or 1
                probe = encode_message(
                    MessageType.DISCOVER, 0, request_id, b""
                ).datagrams[0]
                sent_at_by_request_id[request_id] = time.monotonic()
                for host in targets:
                    try:
                        udp_socket.sendto(probe, (host, port))
                    except (BlockingIOError, OSError):
                        # Unreachable/non-neighbor hosts are expected in a /24.
                        continue
                next_round += 1
                now = time.monotonic()

            next_event = deadline
            if next_round < probe_rounds:
                next_event = min(next_event, round_deadlines[next_round])
            wait_seconds = max(0.0, next_event - time.monotonic())
            readable, _, _ = select.select([udp_socket], [], [], wait_seconds)
            if not readable:
                continue
            while True:
                try:
                    datagram, source = udp_socket.recvfrom(65_535)
                except BlockingIOError:
                    break
                received_at = time.monotonic()
                try:
                    header, body = Header.decode_datagram(datagram)
                    server = _parse_announcement(
                        header,
                        body,
                        source[0],
                        source[1],
                        sent_at_by_request_id,
                        received_at,
                    )
                except ProtocolError:
                    continue
                previous = discovered_by_instance.get(server.instance_id)
                if (
                    previous is None
                    or server.round_trip_milliseconds < previous.round_trip_milliseconds
                ):
                    discovered_by_instance[server.instance_id] = server

        return tuple(
            sorted(
                discovered_by_instance.values(),
                key=lambda server: (
                    not server.accepts_start,
                    server.round_trip_milliseconds,
                    ipaddress.ip_address(server.host),
                ),
            )
        )
    finally:
        udp_socket.close()


def _open_udp_socket(host: str, port: int) -> socket.socket:
    errors: List[OSError] = []
    for family, socktype, protocol, _, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_DGRAM
    ):
        udp_socket = socket.socket(family, socktype, protocol)
        try:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            udp_socket.connect(sockaddr)
            return udp_socket
        except OSError as error:
            errors.append(error)
            udp_socket.close()
    detail = errors[-1] if errors else "no UDP address returned"
    raise OSError(f"could not connect UDP socket to {host}:{port}: {detail}")


class OPIFClient:
    def __init__(self, host: str, port: int) -> None:
        self.socket = _open_udp_socket(host, port)
        self.session: Optional[Session] = None
        self.pipeline_status: Optional[PipelineStatus] = None
        self._control_counter = 0

    def close(self) -> None:
        self.socket.close()

    def _next_control_request_id(self) -> int:
        self._control_counter = (self._control_counter + 1) & 0xFFFF
        return 0xFFFF_FFFF_FFFF_0000 | self._control_counter

    def _send_encoded(
        self, message: EncodedMessage, indices: Optional[Iterable[int]] = None
    ) -> None:
        selected = range(message.fragment_count) if indices is None else indices
        for sent_count, index in enumerate(selected, start=1):
            self.socket.send(message.datagrams[index])
            # A small batch pause avoids overrunning Network.framework's receive
            # queue while keeping a 786 KiB request comfortably below its 0.5 s
            # incomplete-assembly lifetime.
            if sent_count % 16 == 0:
                time.sleep(0.0001)

    def _send_control(
        self,
        message_type: MessageType,
        session_id: int,
        request_id: int,
        body: bytes,
        maximum_datagram_bytes: int = MAXIMUM_DATAGRAM_BYTES,
    ) -> EncodedMessage:
        message = encode_message(
            message_type,
            session_id,
            request_id,
            body,
            maximum_datagram_bytes,
        )
        self._send_encoded(message)
        return message

    def _receive_until(self, deadline: float) -> Optional[Tuple[Header, bytes]]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        self.socket.settimeout(remaining)
        try:
            datagram = self.socket.recv(65_535)
        except socket.timeout:
            return None
        return Header.decode_datagram(datagram)

    @staticmethod
    def _complete_control(
        assemblies: Dict[Tuple[MessageType, int, int], MessageAssembly],
        header: Header,
        payload: bytes,
    ) -> Optional[bytes]:
        key = (header.message_type, header.session_id, header.request_id)
        assembly = assemblies.get(key)
        if assembly is None:
            assembly = MessageAssembly.from_header(header)
            assemblies[key] = assembly
        assembly.add(header, payload)
        body = assembly.complete_body()
        if body is not None:
            del assemblies[key]
        return body

    def _consume_pipeline_status(
        self,
        header: Header,
        payload: bytes,
        assemblies: Dict[Tuple[MessageType, int, int], MessageAssembly],
        session: Session,
    ) -> Optional[PipelineStatus]:
        if header.message_type is not MessageType.PIPELINE_STATUS:
            return None
        if header.session_id != session.session_id:
            return None
        if header.fragment_count != 1 or header.fragment_index != 0:
            raise ProtocolError("PIPELINE_STATUS must use exactly one fragment")
        body = self._complete_control(assemblies, header, payload)
        if body is None:
            return None
        status = _parse_pipeline_status(body)
        if header.request_id != status.revision:
            raise ProtocolError(
                "PIPELINE_STATUS header request ID does not match revision"
            )
        if status.supported_maximum != session.maximum_in_flight:
            raise ProtocolError(
                "PIPELINE_STATUS supported maximum differs from SESSION_READY"
            )
        self.pipeline_status = _select_pipeline_status(
            self.pipeline_status, status
        )
        return status

    @property
    def current_in_flight_limit(self) -> int:
        """Latest active window; stay serial until a valid status is received."""

        if self.session is None:
            return 0
        if self.pipeline_status is None:
            return 1
        return self.pipeline_status.current_depth

    def start_session(
        self, layout: InputLayout, output: OutputEncoding
    ) -> Session:
        client_name = b"python-reference-client"
        start_body = START_PREFIX_STRUCT.pack(
            int(layout),
            0,  # compression: none
            int(output),
            0,
            MAXIMUM_DATAGRAM_BYTES,
            0,
            0,
            len(client_name),
        ) + client_name
        start_request_id = secrets.randbits(64) or 1
        start = encode_message(
            MessageType.START_SESSION, 0, start_request_id, start_body
        )
        deadline = time.monotonic() + getattr(self, "control_timeout", START_TIMEOUT_SECONDS)
        next_start_send = 0.0
        next_ping_send = 0.0
        pending_session_id = 0
        assemblies: Dict[Tuple[MessageType, int, int], MessageAssembly] = {}
        self.pipeline_status = None

        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_start_send:
                self._send_encoded(start)
                next_start_send = now + 1.0
            if now >= next_ping_send:
                ping_id = self._next_control_request_id()
                self._send_control(
                    MessageType.PING,
                    pending_session_id,
                    ping_id,
                    struct.pack("<Q", time.monotonic_ns() & 0xFFFF_FFFF_FFFF_FFFF),
                )
                next_ping_send = now + KEEPALIVE_INTERVAL_SECONDS
            received = self._receive_until(
                min(deadline, next_start_send, next_ping_send)
            )
            if received is None:
                continue
            header, payload = received
            if header.message_type is MessageType.PONG:
                body = self._complete_control(assemblies, header, payload)
                if body is not None and header.session_id != 0:
                    pending_session_id = header.session_id
                continue
            if header.request_id != start_request_id:
                continue
            if header.message_type not in (MessageType.SESSION_READY, MessageType.ERROR):
                continue
            body = self._complete_control(assemblies, header, payload)
            if body is None:
                continue
            if header.message_type is MessageType.ERROR:
                code, expected, message = _parse_error(body)
                if code == 2:
                    raise TransportUnavailable(f"OPIF accelerator is owned or draining: {message}")
                raise ProtocolError(
                    f"START_SESSION failed: code={code}, expected={expected}, {message}"
                )
            if header.session_id == 0:
                raise ProtocolError("SESSION_READY returned session ID zero")
            session = _parse_session_ready(
                body, header.session_id, layout, output
            )
            if not (512 <= session.maximum_datagram_bytes <= MAXIMUM_DATAGRAM_BYTES):
                raise ProtocolError(
                    f"invalid negotiated datagram size {session.maximum_datagram_bytes}"
                )
            self.session = session
            return session
        try:
            self._send_control(
                MessageType.STOP_SESSION,
                pending_session_id,
                self._next_control_request_id(),
                b"",
            )
        except OSError:
            pass
        raise TimeoutError(
            f"timed out after {START_TIMEOUT_SECONDS:g}s waiting for SESSION_READY"
        )

    def ping(self) -> float:
        session = self._require_session()
        request_id = self._next_control_request_id()
        nonce = struct.pack("<Q", time.monotonic_ns() & 0xFFFF_FFFF_FFFF_FFFF)
        ping = encode_message(
            MessageType.PING,
            session.session_id,
            request_id,
            nonce,
            session.maximum_datagram_bytes,
        )
        started = time.monotonic()
        deadline = started + PING_TIMEOUT_SECONDS
        next_send = 0.0
        assemblies: Dict[Tuple[MessageType, int, int], MessageAssembly] = {}
        pong_milliseconds: Optional[float] = None
        status_observed = False
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_send:
                self._send_encoded(ping)
                next_send = now + 0.4
            received = self._receive_until(min(deadline, next_send))
            if received is None:
                continue
            header, payload = received
            if header.message_type is MessageType.PIPELINE_STATUS:
                observed = self._consume_pipeline_status(
                    header, payload, assemblies, session
                ) is not None
                status_observed = status_observed or observed
                if pong_milliseconds is not None and status_observed:
                    return pong_milliseconds
                continue
            if (
                header.session_id != session.session_id
                or header.request_id != request_id
                or header.message_type not in (MessageType.PONG, MessageType.ERROR)
            ):
                continue
            body = self._complete_control(assemblies, header, payload)
            if body is None:
                continue
            if header.message_type is MessageType.ERROR:
                code, expected, message = _parse_error(body)
                raise ProtocolError(
                    f"PING failed: code={code}, expected={expected}, {message}"
                )
            if body != nonce:
                raise ProtocolError("PONG did not echo the PING payload")
            if pong_milliseconds is None:
                pong_milliseconds = (time.monotonic() - started) * 1_000.0
            if status_observed:
                return pong_milliseconds
        missing = "PONG" if pong_milliseconds is None else "PIPELINE_STATUS"
        raise TimeoutError(
            f"timed out after {PING_TIMEOUT_SECONDS:g}s waiting for {missing}"
        )

    def _send_keepalive(self, session: Session) -> None:
        request_id = self._next_control_request_id()
        body = struct.pack("<Q", time.monotonic_ns() & 0xFFFF_FFFF_FFFF_FFFF)
        self._send_control(
            MessageType.PING,
            session.session_id,
            request_id,
            body,
            session.maximum_datagram_bytes,
        )

    def _send_retransmit_query(
        self, session: Session, request: EncodedMessage
    ) -> None:
        body = RETRANSMIT_QUERY_STRUCT.pack(
            MessageType.INFERENCE_REQUEST,
            0,
            request.fragment_count,
            len(request.body),
            request.crc,
        )
        self._send_control(
            MessageType.RETRANSMIT_QUERY,
            session.session_id,
            request.request_id,
            body,
            session.maximum_datagram_bytes,
        )

    def _send_result_query(self, session: Session, request_id: int) -> None:
        body = RETRANSMIT_QUERY_STRUCT.pack(
            MessageType.INFERENCE_RESULT, 0, 0, 0, 0
        )
        self._send_control(
            MessageType.RETRANSMIT_QUERY,
            session.session_id,
            request_id,
            body,
            session.maximum_datagram_bytes,
        )

    def _send_result_nack(
        self, session: Session, request_id: int, assembly: MessageAssembly
    ) -> None:
        body = struct.pack(
            "<BBH", MessageType.INFERENCE_RESULT, 0, assembly.fragment_count
        ) + assembly.missing_bitmap()
        self._send_control(
            MessageType.MISSING_FRAGMENTS,
            session.session_id,
            request_id,
            body,
            session.maximum_datagram_bytes,
        )

    def _send_result_accepted(self, session: Session, request_id: int) -> None:
        self._send_control(
            MessageType.MESSAGE_ACCEPTED,
            session.session_id,
            request_id,
            bytes((MessageType.INFERENCE_RESULT,)),
            session.maximum_datagram_bytes,
        )

    def stop_session(self) -> bool:
        session = self.session
        if session is None:
            return True
        request_id = self._next_control_request_id()
        stop = encode_message(
            MessageType.STOP_SESSION,
            session.session_id,
            request_id,
            b"",
            session.maximum_datagram_bytes,
        )
        deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
        next_send = 0.0
        assemblies: Dict[Tuple[MessageType, int, int], MessageAssembly] = {}
        try:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_send:
                    self._send_encoded(stop)
                    next_send = now + 0.25
                received = self._receive_until(min(deadline, next_send))
                if received is None:
                    continue
                header, payload = received
                if header.message_type is MessageType.PIPELINE_STATUS:
                    self._consume_pipeline_status(
                        header, payload, assemblies, session
                    )
                    continue
                if (
                    header.session_id != session.session_id
                    or header.request_id != request_id
                    or header.message_type is not MessageType.SESSION_STOPPED
                ):
                    continue
                body = self._complete_control(assemblies, header, payload)
                if body is None:
                    continue
                if body:
                    raise ProtocolError("SESSION_STOPPED body must be empty")
                self.session = None
                self.pipeline_status = None
                return True
        finally:
            # A delivered STOP tears down the server even if its ACK was lost.
            self.session = None
            self.pipeline_status = None
        return False

    def _require_session(self) -> Session:
        if self.session is None:
            raise RuntimeError("no active OPIF session")
        return self.session



# Optional native CRC for diagnostic environments. The C3 helper below is
# built with this checkout and is required by the non-diagnostic common client.
FAST_CRC = False
try:
    import crcmod.predefined
    import importlib
    _crc_module = importlib.import_module("crcmod.crcmod")
    if getattr(_crc_module, "_usingExtension", False):
        _native_crc = crcmod.predefined.mkPredefinedCrcFun("crc-32c")
        if _native_crc(b"123456789") != 0xE3069283:
            raise RuntimeError("CRC32C self-test failed")
        crc32c = _native_crc
        FAST_CRC = True
except ImportError:
    pass

# Prefer the helper built with this checkout; diagnostics may retain the portable codec.
from . import native_codec
if native_codec.AVAILABLE:
    crc32c = native_codec.crc32c
    FAST_CRC = True
