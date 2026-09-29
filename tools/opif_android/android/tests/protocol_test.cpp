#include "../native/opif_protocol.h"

#include <arpa/inet.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstring>
#include <deque>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>

namespace {
using opif::Bytes;
using namespace std::chrono_literals;
using Clock = std::chrono::steady_clock;
void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
uint16_t u16(const uint8_t* p) { return uint16_t(p[0]) | uint16_t(p[1]) << 8; }
uint32_t u32(const uint8_t* p) { return uint32_t(u16(p)) | uint32_t(u16(p + 2)) << 16; }
uint64_t u64(const uint8_t* p) { return uint64_t(u32(p)) | uint64_t(u32(p + 4)) << 32; }
void put16(Bytes& b, size_t offset, uint16_t value) { b[offset] = value & 255; b[offset + 1] = value >> 8; }
void put32(Bytes& b, size_t offset, uint32_t value) { put16(b, offset, value & 65535); put16(b, offset + 2, value >> 16); }
void put64(Bytes& b, size_t offset, uint64_t value) { put32(b, offset, uint32_t(value)); put32(b, offset + 4, uint32_t(value >> 32)); }

// This deterministic runtime is linked into tests only; production has no fake
// or fallback inference. Holding its worker proves socket keepalive stays live.
class TestRuntime final : public opif::InferenceRuntime {
 public:
  void begin_session() override {
    ++begins;
    while (hold_begin) std::this_thread::sleep_for(1ms);
    if (fail_begin.exchange(false)) throw std::runtime_error("deliberate test activation failure");
  }
  opif::InferenceResponse infer(const opif::InferenceRequest& request) override {
    ++calls;
    {
      std::lock_guard<std::mutex> lock(mutex);
      last_request = request;
      history.emplace_back(request.request_id, request.reset_temporal);
    }
    while (hold_infer) std::this_thread::sleep_for(1ms);
    if (fail_next.exchange(false)) throw std::runtime_error("deliberate test accelerator failure");
    return {std::vector<float>(opif::kOutputElements, float(request.request_id)), 1234};
  }
  void end_session() noexcept override { ++ends; }
  std::atomic<int> begins{0}, calls{0}, ends{0};
  std::atomic<bool> hold_begin{true}, hold_infer{false}, fail_next{false}, fail_begin{false};
  std::mutex mutex;
  opif::InferenceRequest last_request;
  std::vector<std::pair<uint64_t, bool>> history;
};

struct Message { opif::Header header; Bytes body; };
class Client {
 public:
  explicit Client(uint16_t port, bool stream = false, uint32_t host = INADDR_LOOPBACK) : tcp(stream) {
    fd = socket(AF_INET, stream ? SOCK_STREAM : SOCK_DGRAM, 0); check(fd >= 0, "client socket failed");
    sockaddr_in address{}; address.sin_family = AF_INET; address.sin_addr.s_addr = htonl(host); address.sin_port = htons(port);
    check(connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0, "client connect failed");
    int buffer = 4 * 1024 * 1024;
    setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &buffer, sizeof(buffer));
    setsockopt(fd, SOL_SOCKET, SO_SNDBUF, &buffer, sizeof(buffer));
  }
  ~Client() { disconnect(); }
  void disconnect() { if (fd >= 0) { close(fd); fd = -1; } }
  void send_raw(const Bytes& bytes) {
    size_t offset = 0;
    while (offset < bytes.size()) {
      const ssize_t count = send(fd, bytes.data() + offset, bytes.size() - offset, 0);
      check(count > 0, "client stream send failed"); offset += size_t(count);
    }
  }
  static Bytes framed(const Bytes& packet) {
    Bytes bytes(4); put32(bytes, 0, uint32_t(packet.size()));
    bytes.insert(bytes.end(), packet.begin(), packet.end()); return bytes;
  }
  void expect_disconnect() {
    pollfd descriptor{fd, POLLIN, 0};
    check(poll(&descriptor, 1, 2000) == 1, "server did not disconnect malformed TCP");
    uint8_t byte;
    check(recv(fd, &byte, 1, 0) <= 0, "malformed TCP received unexpected data");
  }
  void send_packet(const Bytes& packet) {
    if (tcp) { send_raw(framed(packet)); return; }
    check(send(fd, packet.data(), packet.size(), 0) == ssize_t(packet.size()), "client send failed");
  }
  void send_message(uint8_t type, uint64_t session, uint64_t request, const Bytes& body, uint16_t maximum = 1232) {
    const auto packets = opif::datagrams(type, session, request, body, maximum);
    if (tcp) {
      Bytes bytes;
      for (const auto& packet : packets) { const auto part = framed(packet); bytes.insert(bytes.end(), part.begin(), part.end()); }
      send_raw(bytes); return;
    }
    for (size_t i = 0; i < packets.size(); ++i) {
      send_packet(packets[i]);
      if (i % 8 == 7) std::this_thread::sleep_for(100us);
    }
  }
  Message receive(uint8_t type, uint64_t request, std::chrono::milliseconds timeout = 2000ms) {
    const auto deadline = Clock::now() + timeout;
    while (true) {
      for (auto it = messages.begin(); it != messages.end(); ++it) if (it->header.type == type && it->header.request_id == request) {
        Message result = std::move(*it); messages.erase(it); return result;
      }
      if (Clock::now() >= deadline) throw std::runtime_error("timed out waiting for type " + std::to_string(type) + " request " + std::to_string(request));
      Bytes packet;
      if (tcp && received.size() >= 4 && received.size() >= 4 + u32(received.data())) {
        const size_t size = u32(received.data());
        check(size >= 40 && size <= 1232, "server TCP frame length invalid");
        packet.assign(received.begin() + 4, received.begin() + 4 + size);
        received.erase(received.begin(), received.begin() + 4 + size);
      } else {
        pollfd descriptor{fd, POLLIN, 0};
        if (poll(&descriptor, 1, 10) != 1) continue;
        uint8_t incoming[65536]; const ssize_t size = recv(fd, incoming, sizeof(incoming), 0);
        check(size > 0, "server disconnected during receive");
        if (tcp) { received.insert(received.end(), incoming, incoming + size); continue; }
        packet.assign(incoming, incoming + size);
      }
      opif::Header header;
      check(opif::decode_header(packet.data(), packet.size(), header), "invalid server header");
      auto& pieces = partial[std::make_tuple(header.type, header.session_id, header.request_id)];
      if (pieces.empty()) pieces.resize(header.fragment_count);
      check(pieces.size() == header.fragment_count, "inconsistent server fragments");
      pieces[header.fragment_index] = Bytes(packet.begin() + 40, packet.end());
      size_t total = 0; bool complete = true;
      for (const auto& piece : pieces) { total += piece.size(); if (piece.empty() && header.message_bytes) complete = false; }
      if (!complete) continue;
      check(total == header.message_bytes, "wrong server message size");
      Bytes body; for (const auto& piece : pieces) body.insert(body.end(), piece.begin(), piece.end());
      check(opif::crc32c(body.data(), body.size()) == header.message_crc32c, "server CRC mismatch");
      messages.push_back({header, std::move(body)});
      partial.erase(std::make_tuple(header.type, header.session_id, header.request_id));
    }
  }
  Message error(uint64_t request, uint16_t code, uint64_t expected = 0) {
    const auto message = receive(255, request);
    check(message.body.size() >= 12 && u16(message.body.data()) == code, "wrong error code");
    check(u64(message.body.data() + 4) == expected, "wrong expected sequence in error");
    return message;
  }
 private:
  int fd;
  bool tcp;
  Bytes received;
  std::map<std::tuple<uint8_t, uint64_t, uint64_t>, std::vector<Bytes>> partial;
  std::deque<Message> messages;
};

Bytes start_body(uint16_t maximum = 1232) { Bytes body(12); put16(body, 4, maximum); return body; }
Bytes request_body(bool reset = false) {
  Bytes body(32 + opif::kTensorBytes, 17);
  std::fill(body.begin(), body.begin() + 32, 0);
  body[2] = 3; body[3] = 1; put16(body, 4, reset ? 1 : 0);
  put32(body, 8, 0x3e800000); put32(body, 12, 0x3fc00000);
  put64(body, 16, 123456789); put32(body, 24, opif::kTensorBytes); put32(body, 28, opif::kTensorBytes);
  return body;
}
Bytes query_body(const std::vector<Bytes>& packets) {
  opif::Header header; check(opif::decode_header(packets[0].data(), packets[0].size(), header), "test header failed");
  Bytes body(12); body[0] = 0x10; put16(body, 2, header.fragment_count);
  put32(body, 4, header.message_bytes); put32(body, 8, header.message_crc32c); return body;
}
void assert_result(const Message& message, uint64_t request) {
  const auto& body = message.body;
  check(body.size() == 24 + 4 * opif::kOutputElements && body[0] == 0 && body[1] == 0 && body[2] == 0, "wrong result layout");
  check(u32(body.data() + 4) == opif::kOutputElements && u32(body.data() + 8) == 1234, "wrong result metadata");
  float value; const uint32_t bits = u32(body.data() + 24); std::memcpy(&value, &bits, 4);
  check(value == float(request), "result is not associated with request");
}

void save_fixture(const std::string& directory, const char* filename, const Bytes& data) {
  if (directory.empty()) return;
  std::ofstream output(directory + "/" + filename, std::ios::binary);
  output.write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
  check(bool(output), "cannot write interoperability fixture");
}

void integration(opif::UdpServer& server, TestRuntime& runtime, const std::string& fixture_directory) {
#ifdef __linux__
  // A wildcard listener must reply from the destination used by this connected
  // client, including delayed results and repairs, rather than loopback's .1.
  Client client(server.port(), false, 0x7f000002), stranger(server.port());
#else
  Client client(server.port()), stranger(server.port());
#endif
  client.send_message(7, 0, 10, {});
  auto announce = client.receive(0x84, 10);
  check(announce.body.size() == 24 && announce.body[1] == 0 && u16(announce.body.data() + 2) == 1, "discovery unavailable");
  check(runtime.begins == 0, "discovery woke model");
  auto bad_start = start_body(); bad_start[0] = 1;
  client.send_message(1, 0, 11, bad_start); client.error(11, 1);
  bad_start = start_body(); bad_start[2] = 1;
  client.send_message(1, 0, 12, bad_start); client.error(12, 1);
  auto corrupt = opif::datagrams(1, 0, 13, start_body(), 1232)[0]; corrupt.back() ^= 1;
  client.send_packet(corrupt); client.error(13, 1);

  client.send_message(1, 0, 20, start_body());
  client.send_message(3, 0, 21, Bytes{1, 2, 3});
  const auto pending = client.receive(0x83, 21);
  check(pending.header.session_id != 0 && pending.body == Bytes({1, 2, 3}), "pending PONG failed");
  client.send_message(1, 0, 22, start_body());
  stranger.send_message(1, 0, 23, start_body());
  check(stranger.error(23, 2).header.session_id == 0, "busy START ERROR exposed pending session ID");
  stranger.send_message(7, 0, 24, {});
  check(stranger.receive(0x84, 24).body[1] == 1, "pending discovery state wrong");
  runtime.hold_begin = false;
  auto ready = client.receive(0x81, 20);
  const uint64_t session = ready.header.session_id;
  check(session == pending.header.session_id && u32(ready.body.data() + 8) == opif::kTensorBytes, "READY session/tensor mismatch");
  check(ready.body.size() >= 30 && ready.body[25] == 2 && u16(ready.body.data() + 20) == 32 && u16(ready.body.data() + 22) == 33 && ready.body[24] == 4, "READY temporal ABI mismatch");
  check(std::string(ready.body.begin() + 30 + u16(ready.body.data() + 26), ready.body.end()) == opif::kABI, "READY source ABI mismatch");
  save_fixture(fixture_directory, "ready.bin", ready.body);
  check(client.receive(0x85, 1).body == Bytes({1, 2, 2, 0, 1, 0, 0, 0, 0, 0, 0, 0}), "pipeline status mismatch");
  client.send_message(1, 0, 25, start_body());
  check(client.receive(0x81, 25).body == ready.body && runtime.begins == 1, "duplicate START reloaded runtime");

  // Handshake ERROR headers correlate with START's session field, including
  // malformed STARTs received while a different session is active.
  stranger.send_message(1, 0, 1001, bad_start);
  check(stranger.error(1001, 1).header.session_id == 0, "malformed START ERROR exposed active session ID");
  stranger.send_message(1, 123456, 1002, start_body());
  check(stranger.error(1002, 1).header.session_id == 123456, "malformed START ERROR did not preserve requested session ID");
  stranger.send_message(1, 0, 1003, start_body());
  check(stranger.error(1003, 2).header.session_id == 0, "busy START ERROR exposed active session ID");

  // Ignore source-port forgery even with the actual session ID.
  stranger.send_message(2, session, 26, {});
  client.send_message(3, session, 27, Bytes{9});
  check(client.receive(0x83, 27).body == Bytes({9}), "owner changed after forged STOP");

  const auto body = request_body();
  auto packets = opif::datagrams(0x10, session, 1, body, 1232);
  // Deliberately leave fragment 3 missing, then repair it through the bitmap.
  for (size_t i = 0; i < packets.size(); ++i) if (i != 3) {
    client.send_packet(packets[i]); if (i % 8 == 7) std::this_thread::sleep_for(100us);
  }
  client.send_message(4, session, 1, query_body(packets));
  const auto missing = client.receive(5, 1);
  check(missing.body[4] == 8, "request missing-fragment bitmap incorrect");
  runtime.hold_infer = true; client.send_packet(packets[3]);
  check(client.receive(6, 1).body == Bytes({0x10}), "admission ACK wrong");
  client.send_packet(packets[0]); client.receive(6, 1);
  client.send_message(3, session, 28, Bytes{7}); client.receive(0x83, 28);
  runtime.hold_infer = false;
  const auto first = client.receive(0x90, 1); assert_result(first, 1);
  save_fixture(fixture_directory, "result.bin", first.body);
  {
    std::lock_guard<std::mutex> lock(runtime.mutex);
    check(runtime.last_request.action_t[0] == 0.25f && runtime.last_request.action_t[1] == 1.5f &&
          runtime.last_request.desire == 3 && runtime.last_request.traffic_convention == 1 &&
          runtime.last_request.client_timestamp_ns == 123456789 && runtime.last_request.tensor.size() == opif::kTensorBytes &&
          runtime.last_request.tensor.front() == 17 && !runtime.last_request.reset_temporal, "runtime inputs changed");
  }
  client.send_packet(packets[0]); assert_result(client.receive(0x90, 1), 1);
  check(runtime.calls == 1, "duplicate request re-executed runtime");
  Bytes result_query(12); result_query[0] = 0x90;
  client.send_message(4, session, 1, result_query); assert_result(client.receive(0x90, 1), 1);

  // Request selective terminal repair (all bits requested here so the test
  // independently reassembles and CRC-checks the replayed output).
  Bytes result_missing(4 + (first.header.fragment_count + 7) / 8, 255);
  result_missing[0] = 0x90; result_missing[1] = 0; put16(result_missing, 2, first.header.fragment_count);
  client.send_message(5, session, 1, result_missing); assert_result(client.receive(0x90, 1), 1);

  client.send_message(0x10, session, 3, body); client.error(3, 8, 2);
  auto malformed = body; put32(malformed, 8, 0x7fc00000);
  client.send_message(0x10, session, 2, malformed); client.error(2, 10, 2);
  runtime.fail_next = true;
  client.send_message(0x10, session, 2, body); client.receive(6, 2); client.error(2, 11, 3);
  client.send_message(4, session, 2, result_query); client.error(2, 11, 3);
  client.send_message(0x10, session, 3, body); client.error(3, 10, 3);
  client.send_message(0x10, session, 3, request_body(true)); client.receive(6, 3); assert_result(client.receive(0x90, 3), 3);

  // Assemblies expire without consuming an ID; repair then requests every bit.
  packets = opif::datagrams(0x10, session, 4, body, 1232);
  for (uint64_t id = 4; id <= 10; ++id)
    client.send_packet(opif::datagrams(0x10, session, id, body, 1232)[0]);
  client.error(10, 5);
  std::this_thread::sleep_for(650ms);
  client.send_message(4, session, 4, query_body(packets));
  check(client.receive(5, 4).body[4] == 255, "expired assembly was retained");
  // Conflicting duplicate fragment and whole-message CRC checks.
  client.send_packet(packets[0]); auto conflicting = packets[0]; conflicting.back() ^= 1;
  client.send_packet(conflicting); client.error(4, 6);
  auto bad_crc = packets;
  for (auto& packet : bad_crc) packet[36] ^= 1;
  for (size_t i = 0; i < bad_crc.size(); ++i) { client.send_packet(bad_crc[i]); if (i % 8 == 7) std::this_thread::sleep_for(100us); }
  client.error(4, 7);
  for (uint64_t id = 4; id <= 35; ++id) {
    client.send_message(0x10, session, id, body); client.receive(6, id); assert_result(client.receive(0x90, id), id);
  }
  client.send_message(4, session, 1, result_query); client.error(1, 12, 36);
  client.send_message(2, session, 29, {});
  check(client.receive(0x82, 29).header.session_id == session, "STOP session mismatch");
  std::this_thread::sleep_for(20ms);
  check(runtime.ends == 1, "STOP did not release runtime state");
  check(!server.draining(), "ordinary client STOP retired the listener");

  // Minimum-MTU clamping is advertised and honored, then active lease expires.
  client.send_message(1, 0, 30, start_body(0));
  ready = client.receive(0x81, 30);
  check(u16(ready.body.data() + 4) == 512, "minimum MTU negotiation failed");
  const uint64_t next_session = ready.header.session_id;
  client.send_message(0x10, next_session, 1, body, 512); client.receive(6, 1); assert_result(client.receive(0x90, 1), 1);
  std::this_thread::sleep_for(5200ms);
  stranger.send_message(7, 0, 31, {});
  check(stranger.receive(0x84, 31).body[1] == 0 && runtime.ends == 2, "active lease did not end session");

  // STOP invalidates an executing generation immediately, but must drain its
  // buffers before a new model session may begin.
  client.send_message(1, 0, 40, start_body());
  const uint64_t draining_session = client.receive(0x81, 40).header.session_id;
  runtime.hold_infer = true;
  client.send_message(0x10, draining_session, 1, body); client.receive(6, 1);
  client.send_message(2, draining_session, 41, {}); client.receive(0x82, 41);
  stranger.send_message(1, 0, 42, start_body()); stranger.error(42, 2);
  runtime.hold_infer = false;
  for (unsigned count = 0; count < 1000 && runtime.ends < 3; ++count) std::this_thread::sleep_for(1ms);
  check(runtime.ends == 3, "in-flight STOP did not drain the runtime");

  // Model activation errors also correlate with the original START session 0.
  std::this_thread::sleep_for(10ms);
  runtime.fail_begin = true;
  client.send_message(1, 0, 45, start_body());
  check(client.error(45, 4).header.session_id == 0, "activation ERROR exposed generated session ID");
}

void tcp_integration(opif::UdpServer& server, TestRuntime& runtime) {
  Client udp(server.port()), tcp(server.port(), true), other(server.port(), true);
  const auto wait_idle = [&] {
    for (unsigned attempt = 0; attempt < 200; ++attempt) {
      udp.send_message(7, 0, 9000, {});
      if (udp.receive(0x84, 9000).body[1] == 0) return;
      std::this_thread::sleep_for(2ms);
    }
    throw std::runtime_error("disconnected session never drained");
  };
  wait_idle();

  // Prefix/body may be split anywhere, and multiple framed datagrams may arrive
  // in a single write. None of these TCP boundaries are OPIF boundaries.
  const auto discover = Client::framed(opif::datagrams(7, 0, 100, {}, 1232)[0]);
  tcp.send_raw(Bytes(discover.begin(), discover.begin() + 2));
  std::this_thread::sleep_for(10ms);
  tcp.send_raw(Bytes(discover.begin() + 2, discover.begin() + 15));
  std::this_thread::sleep_for(10ms);
  tcp.send_raw(Bytes(discover.begin() + 15, discover.end()));
  check(tcp.receive(0x84, 100).body[1] == 0, "split TCP discovery failed");
  auto combined = Client::framed(opif::datagrams(7, 0, 101, {}, 1232)[0]);
  const auto second = Client::framed(opif::datagrams(7, 0, 102, {}, 1232)[0]);
  combined.insert(combined.end(), second.begin(), second.end()); tcp.send_raw(combined);
  tcp.receive(0x84, 101); tcp.receive(0x84, 102);

  // UDP and TCP listeners share one model owner, even on the same source IP.
  udp.send_message(1, 0, 103, start_body());
  const uint64_t udp_session = udp.receive(0x81, 103).header.session_id;
  tcp.send_message(1, 0, 104, start_body()); tcp.error(104, 2);
  tcp.send_message(2, udp_session, 105, {});
  udp.send_message(3, udp_session, 106, Bytes{6}); udp.receive(0x83, 106);
  udp.send_message(2, udp_session, 107, {}); udp.receive(0x82, 107); wait_idle();

  // Disconnect during activation cancels that generation but cannot overlap
  // a new session with the worker's unfinished begin_session call.
  runtime.hold_begin = true;
  tcp.send_message(1, 0, 108, start_body());
  tcp.send_message(3, 0, 109, {}); tcp.receive(0x83, 109);
  tcp.disconnect();
  std::this_thread::sleep_for(20ms);
  udp.send_message(1, 0, 110, start_body()); udp.error(110, 2);
  runtime.hold_begin = false; wait_idle();

  Client owner(server.port(), true);
  owner.send_message(1, 0, 111, start_body());
  const uint64_t session = owner.receive(0x81, 111).header.session_id;
  udp.send_message(1, 0, 112, start_body()); udp.error(112, 2);
  other.send_message(1, 0, 113, start_body()); other.error(113, 2);
  other.send_message(2, session, 114, {});
  udp.send_message(2, session, 115, {});
  owner.send_message(3, session, 116, Bytes{7}); owner.receive(0x83, 116);

  // Batch the entire 393 KiB tensor over TCP and parse the real fragmented
  // result with the same CRC/ABI checks as the UDP integration suite.
  owner.send_message(0x10, session, 1, request_body(true));
  owner.receive(6, 1); assert_result(owner.receive(0x90, 1), 1);
  Bytes result_query(12); result_query[0] = 0x90;
  owner.send_message(4, session, 1, result_query); assert_result(owner.receive(0x90, 1), 1);
  auto corrupt = opif::datagrams(0x10, session, 2, request_body(), 1232);
  for (auto& packet : corrupt) packet[36] ^= 1;
  Bytes corrupted_bytes;
  for (const auto& packet : corrupt) {
    const auto framed = Client::framed(packet);
    corrupted_bytes.insert(corrupted_bytes.end(), framed.begin(), framed.end());
  }
  owner.send_raw(corrupted_bytes); owner.error(2, 7);

  // Reject invalid length/header before allocating an unbounded stream buffer;
  // disconnecting those non-owners must leave the actual owner alive.
  for (uint32_t length : {0u, 39u, 1233u, 0xffffffffu}) {
    Client invalid(server.port(), true); Bytes prefix(4); put32(prefix, 0, length);
    invalid.send_raw(prefix); invalid.expect_disconnect();
  }
  {
    Client invalid(server.port(), true); invalid.send_raw(Client::framed(Bytes(40)));
    invalid.expect_disconnect();
  }
  owner.send_message(3, session, 117, {}); owner.receive(0x83, 117);

  const int calls_before_hold = runtime.calls;
  runtime.hold_infer = true;
  owner.send_message(0x10, session, 2, request_body()); owner.receive(6, 2);
  for (unsigned count = 0; count < 500 && runtime.calls == calls_before_hold; ++count) std::this_thread::sleep_for(1ms);
  check(runtime.calls == calls_before_hold + 1, "TCP held inference did not start");
  owner.send_message(0x10, session, 3, request_body()); owner.receive(6, 3);
  const int calls_before_disconnect = runtime.calls;
  owner.disconnect(); std::this_thread::sleep_for(20ms);
  udp.send_message(1, 0, 118, start_body()); udp.error(118, 2);
  runtime.hold_infer = false; wait_idle();
  check(runtime.calls == calls_before_disconnect, "TCP disconnect executed queued frame");
  udp.send_message(1, 0, 119, start_body());
  const uint64_t fresh_session = udp.receive(0x81, 119).header.session_id;
  check(fresh_session != session, "TCP disconnect reused prior session");
  udp.send_message(0x10, fresh_session, 1, request_body(true));
  udp.receive(6, 1); assert_result(udp.receive(0x90, 1), 1);
  udp.send_message(2, fresh_session, 120, {}); udp.receive(0x82, 120); wait_idle();
}

void depth_two_integration(opif::UdpServer& server, TestRuntime& runtime, bool tcp) {
  Client client(server.port(), tcp), observer(server.port());
  const auto wait_idle = [&] {
    for (unsigned attempt = 0; attempt < 200; ++attempt) {
      observer.send_message(7, 0, 9100, {});
      if (observer.receive(0x84, 9100).body[1] == 0) return;
      std::this_thread::sleep_for(2ms);
    }
    throw std::runtime_error("depth-2 session never drained");
  };
  const auto wait_calls = [&](int count) {
    for (unsigned attempt = 0; attempt < 500 && runtime.calls < count; ++attempt)
      std::this_thread::sleep_for(1ms);
    check(runtime.calls == count, "wrong number of serial runtime calls");
  };
  wait_idle();
  client.send_message(1, 0, 200, start_body());
  const auto ready = client.receive(0x81, 200);
  const uint64_t session = ready.header.session_id;
  check(ready.body[25] == 2, "depth-2 READY not advertised");
  const auto status = client.receive(0x85, 1);
  check(status.body[1] == 2 && status.body[2] == 2, "depth-2 active window not advertised");
  const int initial_calls = runtime.calls;
  size_t history_start;
  { std::lock_guard<std::mutex> lock(runtime.mutex); history_start = runtime.history.size(); }

  runtime.hold_infer = true;
  client.send_message(0x10, session, 1, request_body()); client.receive(6, 1);
  wait_calls(initial_calls + 1);
  client.send_message(0x10, session, 2, request_body(true)); client.error(2, 9, 2);
  client.send_message(0x10, session, 2, request_body()); client.receive(6, 2);
  Bytes query(12); query[0] = 0x90;
  client.send_message(4, session, 2, query); client.receive(6, 2);
  client.send_packet(opif::datagrams(0x10, session, 2, request_body(), 1232)[0]); client.receive(6, 2);
  check(runtime.calls == initial_calls + 1, "queued request ran before preceding inference completed");

  // Partial prefetch remains legal while both inference credits are occupied.
  const auto third = opif::datagrams(0x10, session, 3, request_body(), 1232);
  client.send_packet(third[0]);
  client.send_message(4, session, 3, query_body(third));
  check(client.receive(5, 3).body[4] == 254, "depth-2 partial prefetch was not retained");
  client.send_message(0x10, session, 3, request_body()); client.error(3, 9, 3);
  check(runtime.calls == initial_calls + 1, "third request bypassed the bounded queue");
  runtime.hold_infer = false;
  assert_result(client.receive(0x90, 1), 1); assert_result(client.receive(0x90, 2), 2);
  wait_calls(initial_calls + 2);
  {
    std::lock_guard<std::mutex> lock(runtime.mutex);
    check(runtime.history[history_start] == std::make_pair(uint64_t(1), false) &&
          runtime.history[history_start + 1] == std::make_pair(uint64_t(2), false),
          "queue order changed or rejected RESET executed");
  }
  client.send_message(0x10, session, 3, request_body()); client.receive(6, 3);
  assert_result(client.receive(0x90, 3), 3);  // A full-window error consumed no ID.

  runtime.hold_infer = true; runtime.fail_next = true;
  client.send_message(0x10, session, 4, request_body()); client.receive(6, 4);
  wait_calls(initial_calls + 4);
  client.send_message(0x10, session, 5, request_body()); client.receive(6, 5);
  runtime.hold_infer = false;
  client.error(4, 11, 6); client.error(5, 11, 6);
  check(runtime.calls == initial_calls + 4, "prior failure executed queued input against damaged state");
  for (uint64_t id : {4u, 5u}) { client.send_message(4, session, id, query); client.error(id, 11, 6); }
  client.send_message(0x10, session, 6, request_body()); client.error(6, 10, 6);

  runtime.hold_infer = true;
  client.send_message(0x10, session, 6, request_body(true)); client.receive(6, 6);
  wait_calls(initial_calls + 5);
  client.send_message(0x10, session, 7, request_body()); client.receive(6, 7);
  runtime.hold_infer = false;
  assert_result(client.receive(0x90, 6), 6); assert_result(client.receive(0x90, 7), 7);
  wait_calls(initial_calls + 6);
  {
    std::lock_guard<std::mutex> lock(runtime.mutex);
    check(runtime.history[history_start + 4] == std::make_pair(uint64_t(6), true) &&
          runtime.history[history_start + 5] == std::make_pair(uint64_t(7), false),
          "recovery RESET did not precede queued continuation");
  }

  runtime.hold_infer = true;
  client.send_message(0x10, session, 8, request_body()); client.receive(6, 8);
  wait_calls(initial_calls + 7);
  client.send_message(0x10, session, 9, request_body()); client.receive(6, 9);
  client.send_message(2, session, 201, {}); client.receive(0x82, 201);
  observer.send_message(1, 0, 202, start_body()); observer.error(202, 2);
  runtime.hold_infer = false; wait_idle();
  check(runtime.calls == initial_calls + 7, "STOP started a queued frame instead of discarding it");
}

int shutdown_with_queue(opif::UdpServer& server, TestRuntime& runtime, std::atomic<bool>& stop) {
  Client client(server.port(), true);
  client.send_message(1, 0, 300, start_body());
  const uint64_t session = client.receive(0x81, 300).header.session_id;
  const int expected_calls = runtime.calls + 1;
  runtime.hold_infer = true;
  client.send_message(0x10, session, 1, request_body()); client.receive(6, 1);
  for (unsigned count = 0; count < 500 && runtime.calls < expected_calls; ++count) std::this_thread::sleep_for(1ms);
  check(runtime.calls == expected_calls, "shutdown inference did not start");
  client.send_message(0x10, session, 2, request_body()); client.receive(6, 2);
  stop = true;
  runtime.hold_infer = false;
  // Keep the TCP connection open until the server has observed the stop flag,
  // so this verifies global shutdown rather than EOF cancellation.
  std::this_thread::sleep_for(150ms);
  return expected_calls;
}

void selected_transport_integration(opif::Transport mode) {
  TestRuntime runtime;
  runtime.hold_begin = false;
  std::atomic<bool> stop{false}, returned{false};
  std::atomic<int> desired{int(mode)};
  std::exception_ptr server_error;
  uint16_t used_port = 0;
  {
    opif::UdpServer server(runtime, 0, mode);
    used_port = server.port();
    check(used_port != 0, "selected listener did not allocate ephemeral port");
    // Disabled transport must not own the port, not merely ignore its packets.
    const int disabled_type = mode == opif::Transport::Udp ? SOCK_STREAM : SOCK_DGRAM;
    const int disabled = socket(AF_INET, disabled_type, 0);
    check(disabled >= 0, "disabled-transport test socket failed");
    sockaddr_in address{}; address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY; address.sin_port = htons(used_port);
    const bool bound = bind(disabled, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0;
    close(disabled);
    check(bound, "disabled transport still reserves its port");

    std::thread thread([&] {
      try { server.run(stop, &desired); } catch (...) { server_error = std::current_exception(); }
      returned = true;
    });
    try {
      Client client(used_port, mode == opif::Transport::Tcp);
      client.send_message(1, 0, 400, start_body());
      const auto ready = client.receive(0x81, 400);
      check(ready.body[25] == 2, "selected transport handshake changed depth");
      client.send_message(3, ready.header.session_id, 401, Bytes{4, 0, 1});
      check(client.receive(0x83, 401).body == Bytes({4, 0, 1}), "selected transport PING failed");

      runtime.hold_infer = true;
      client.send_message(0x10, ready.header.session_id, 1, request_body()); client.receive(6, 1);
      for (unsigned count = 0; count < 500 && runtime.calls < 1; ++count) std::this_thread::sleep_for(1ms);
      check(runtime.calls == 1, "transport-switch inference did not start");
      client.send_message(0x10, ready.header.session_id, 2, request_body()); client.receive(6, 2);
      desired = int(mode == opif::Transport::Udp ? opif::Transport::Tcp : opif::Transport::Udp);
      for (unsigned count = 0; count < 500 && !server.draining(); ++count) std::this_thread::sleep_for(1ms);
      check(server.draining() && !returned && runtime.ends == 0, "mode switch returned before accelerator drain");
      if (mode == opif::Transport::Tcp) {
        desired = int(mode);  // A -> B -> A after drain began must stay retired.
        check(server.draining(), "transport ABA revived the old listener");
      }
      runtime.hold_infer = false;
      for (unsigned count = 0; count < 1000 && !returned; ++count) std::this_thread::sleep_for(1ms);
      check(returned && !stop, "mode change did not return independently of stop");
      thread.join();
    } catch (...) {
      runtime.hold_begin = false; runtime.hold_infer = false; stop = true;
      if (thread.joinable()) thread.join();
      throw;
    }
    if (server_error) std::rethrow_exception(server_error);
    check(runtime.calls == 1 && runtime.ends == 1, "mode switch executed waiting frame or failed to end session");
  }
  // Reuse the same runtime and numeric port after the old listener's scope.
  // This is the app's warm transport switch; it does not reconstruct a model.
  {
    const auto next_mode = opif::Transport(desired.load());
    opif::UdpServer next(runtime, used_port, next_mode);
    check(next.port() == used_port, "warm transport switch changed port");
    desired = int(next_mode == opif::Transport::Udp ? opif::Transport::Tcp : opif::Transport::Udp);
    const auto started = Clock::now();
    next.run(stop, &desired);
    check(next.draining() && Clock::now() - started < 100ms && runtime.begins == 1,
          "pre-run mode change started another model session");
  }
}

void invalid_transport_rejected() {
  TestRuntime runtime;
  for (int value : {0, -1, 4}) {
    bool rejected = false;
    try { opif::UdpServer server(runtime, 0, opif::Transport(value)); }
    catch (const std::invalid_argument&) { rejected = true; }
    check(rejected, "invalid listener transport accepted");
  }
}
}  // namespace

int main(int argc, char** argv) {
  try {
    const std::string known = "123456789";
    check(opif::crc32c(reinterpret_cast<const uint8_t*>(known.data()), known.size()) == 0xe3069283, "CRC32C vector failed");
    check(opif::crc32c(nullptr, 0) == 0, "empty CRC32C failed");
    opif::Header header;
    Bytes invalid(40); check(!opif::decode_header(invalid.data(), invalid.size(), header), "invalid header accepted");
    auto empty = opif::datagrams(7, 0, 1, {}, 512)[0];
    check(opif::decode_header(empty.data(), empty.size(), header) && header.message_bytes == 0 && header.fragment_count == 1, "empty message failed");
    invalid_transport_rejected();
    selected_transport_integration(opif::Transport::Udp);
    selected_transport_integration(opif::Transport::Tcp);
    TestRuntime runtime;
    opif::UdpServer server(runtime, 0);
    std::atomic<bool> stop{false};
    std::exception_ptr server_error;
    int shutdown_expected_calls = -1;
    std::thread thread([&] { try { server.run(stop); } catch (...) { server_error = std::current_exception(); } });
    try {
      integration(server, runtime, argc == 2 ? argv[1] : "");
      tcp_integration(server, runtime);
      depth_two_integration(server, runtime, false);
      depth_two_integration(server, runtime, true);
      shutdown_expected_calls = shutdown_with_queue(server, runtime, stop);
    }
    catch (...) {
      runtime.hold_begin = false; runtime.hold_infer = false; stop = true; thread.join(); throw;
    }
    stop = true; thread.join();
    if (server_error) std::rethrow_exception(server_error);
    check(runtime.calls == shutdown_expected_calls, "global shutdown promoted queued inference");
    std::cout << "OPIF protocol tests passed (real UDP + framed TCP; test-only runtime)\n";
  } catch (const std::exception& error) {
    std::cerr << "protocol_test: " << error.what() << '\n'; return 1;
  }
}
