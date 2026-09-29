#include "opif_protocol.h"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <deque>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace opif {
namespace {
constexpr uint8_t Start = 1, Stop = 2, Ping = 3, Query = 4, Missing = 5,
                  Accepted = 6, Discover = 7, Infer = 0x10, Ready = 0x81,
                  Stopped = 0x82, Pong = 0x83, Announce = 0x84,
                  PipelineStatus = 0x85, Result = 0x90, Error = 0xff;
using Clock = std::chrono::steady_clock;
using Time = Clock::time_point;
uint16_t u16(const uint8_t* p) { return uint16_t(p[0]) | uint16_t(p[1]) << 8; }
uint32_t u32(const uint8_t* p) { return uint32_t(u16(p)) | uint32_t(u16(p + 2)) << 16; }
uint64_t u64(const uint8_t* p) { return uint64_t(u32(p)) | uint64_t(u32(p + 4)) << 32; }
void put16(Bytes& b, uint16_t n) { b.push_back(n & 255); b.push_back(n >> 8); }
void put32(Bytes& b, uint32_t n) { put16(b, n & 65535); put16(b, n >> 16); }
void put64(Bytes& b, uint64_t n) { put32(b, uint32_t(n)); put32(b, uint32_t(n >> 32)); }
float f32(const uint8_t* p) { uint32_t n = u32(p); float f; std::memcpy(&f, &n, 4); return f; }
uint64_t uptime_ns() {
  return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
}
uint64_t nonce() {
  std::random_device random;
  uint64_t value = (uint64_t(random()) << 32) ^ random();
  return value ? value : 1;
}
struct Peer {
  sockaddr_in address{};
  uint64_t connection = 0;  // Zero means UDP; TCP identities never reuse an fd.
#ifdef __linux__
  int interface_index = 0;
  in_addr local_address{};
#endif
};
bool same_peer(const Peer& a, const Peer& b) {
  if (a.connection || b.connection) return a.connection == b.connection;
  return
#ifdef __linux__
    a.interface_index == b.interface_index && a.local_address.s_addr == b.local_address.s_addr &&
#endif
    a.address.sin_family == b.address.sin_family &&
    a.address.sin_addr.s_addr == b.address.sin_addr.s_addr && a.address.sin_port == b.address.sin_port;
}
bool utf8(const uint8_t* p, size_t size) {
  for (size_t i = 0; i < size;) {
    uint32_t c = p[i++];
    if (c < 0x80) continue;
    unsigned n; uint32_t minimum;
    if (c >= 0xc2 && c <= 0xdf) { n = 1; minimum = 0x80; c &= 31; }
    else if (c >= 0xe0 && c <= 0xef) { n = 2; minimum = 0x800; c &= 15; }
    else if (c >= 0xf0 && c <= 0xf4) { n = 3; minimum = 0x10000; c &= 7; }
    else return false;
    if (i + n > size) return false;
    while (n--) { if ((p[i] & 0xc0) != 0x80) return false; c = (c << 6) | (p[i++] & 63); }
    if (c < minimum || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) return false;
  }
  return true;
}
Bytes error_body(uint16_t code, uint64_t expected, const std::string& text) {
  // Errors must remain single-fragment controls at the smallest negotiated MTU.
  const size_t count = std::min<size_t>(text.size(), kMinimumDatagramBytes - kHeaderBytes - 12);
  Bytes b; put16(b, code); put16(b, uint16_t(count)); put64(b, expected);
  b.insert(b.end(), text.begin(), text.begin() + count); return b;
}
void nonblocking(int fd) {
  const int flags = fcntl(fd, F_GETFL);
  if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0 || fcntl(fd, F_SETFD, FD_CLOEXEC) < 0)
    throw std::runtime_error("cannot configure OPIF file descriptor");
}
}  // namespace

uint32_t crc32c(const uint8_t* data, size_t size) {
  static const auto table = [] {
    std::array<uint32_t, 256> values{};
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t value = i;
      for (unsigned bit = 0; bit < 8; ++bit) value = (value >> 1) ^ ((value & 1) ? 0x82f63b78 : 0);
      values[i] = value;
    }
    return values;
  }();
  uint32_t value = 0xffffffff;
  for (size_t i = 0; i < size; ++i) value = table[(value ^ data[i]) & 255] ^ (value >> 8);
  return value ^ 0xffffffff;
}

bool decode_header(const uint8_t* p, size_t size, Header& h) {
  if (size < kHeaderBytes || size > kMaximumDatagramBytes ||
      std::memcmp(p, "OPIF", 4) || p[4] != 1 || u16(p + 6) != 0 ||
      u16(p + 8) != kHeaderBytes || u16(p + 10) != size - kHeaderBytes) return false;
  h = {p[5], u16(p + 10), u64(p + 12), u64(p + 20), u16(p + 28),
       u16(p + 30), u32(p + 32), u32(p + 36)};
  return h.fragment_count && h.fragment_index < h.fragment_count &&
         h.message_bytes <= kMaximumMessageBytes;
}

std::vector<Bytes> datagrams(uint8_t type, uint64_t session, uint64_t request,
                           const Bytes& body, uint16_t maximum) {
  if (maximum < kMinimumDatagramBytes || maximum > kMaximumDatagramBytes || body.size() > kMaximumMessageBytes)
    throw std::invalid_argument("OPIF message or datagram size out of range");
  const size_t limit = maximum - kHeaderBytes;
  const size_t count = std::max<size_t>(1, (body.size() + limit - 1) / limit);
  const uint32_t crc = crc32c(body.data(), body.size());
  std::vector<Bytes> packets; packets.reserve(count);
  for (size_t index = 0; index < count; ++index) {
    const size_t begin = index * limit, end = std::min(body.size(), begin + limit);
    Bytes b{'O', 'P', 'I', 'F', 1, type}; b.reserve(kHeaderBytes + end - begin);
    put16(b, 0); put16(b, kHeaderBytes); put16(b, uint16_t(end - begin));
    put64(b, session); put64(b, request); put16(b, uint16_t(index)); put16(b, uint16_t(count));
    put32(b, uint32_t(body.size())); put32(b, crc);
    b.insert(b.end(), body.begin() + begin, body.begin() + end); packets.push_back(std::move(b));
  }
  return packets;
}

class UdpServer::Impl {
 public:
  Impl(InferenceRuntime& runtime, uint16_t port, Transport transport)
      : runtime_(runtime), transport_(transport), instance_(nonce()) {
    if (transport != Transport::Udp && transport != Transport::Tcp && transport != Transport::Both)
      throw std::invalid_argument("invalid OPIF listener transport");
    try {
      sockaddr_in address{}; address.sin_family = AF_INET; address.sin_addr.s_addr = INADDR_ANY; address.sin_port = htons(port);
      if (transport != Transport::Tcp) {
        fd_ = socket(AF_INET, SOCK_DGRAM, 0);
        if (fd_ < 0) throw std::runtime_error("cannot create OPIF UDP socket");
        nonblocking(fd_);
#ifdef __linux__
        // Android routes an unbound UDP reply over its default network, even
        // when the request arrived over USB Ethernet. Keep each packet's path.
        int packet_info = 1;
        if (setsockopt(fd_, IPPROTO_IP, IP_PKTINFO, &packet_info, sizeof(packet_info)) != 0)
          throw std::runtime_error("cannot enable OPIF UDP packet info: " + std::string(std::strerror(errno)));
#endif
        int buffer = 4 * 1024 * 1024;
        setsockopt(fd_, SOL_SOCKET, SO_RCVBUF, &buffer, sizeof(buffer));
        setsockopt(fd_, SOL_SOCKET, SO_SNDBUF, &buffer, sizeof(buffer));
        if (bind(fd_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0)
          throw std::runtime_error("cannot bind OPIF UDP port: " + std::string(std::strerror(errno)));
        socklen_t size = sizeof(address);
        if (getsockname(fd_, reinterpret_cast<sockaddr*>(&address), &size) != 0)
          throw std::runtime_error("cannot inspect OPIF UDP socket");
      }
      if (transport != Transport::Udp) {
        tcp_fd_ = socket(AF_INET, SOCK_STREAM, 0);
        if (tcp_fd_ < 0) throw std::runtime_error("cannot create OPIF TCP socket");
        nonblocking(tcp_fd_);
        int reuse = 1;
        setsockopt(tcp_fd_, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
        if (bind(tcp_fd_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 || listen(tcp_fd_, 8) != 0)
          throw std::runtime_error("cannot bind/listen OPIF TCP port: " + std::string(std::strerror(errno)));
        socklen_t size = sizeof(address);
        if (getsockname(tcp_fd_, reinterpret_cast<sockaddr*>(&address), &size) != 0)
          throw std::runtime_error("cannot inspect OPIF TCP socket");
      }
      port_ = ntohs(address.sin_port);
      if (pipe(wake_) != 0) throw std::runtime_error("cannot create OPIF worker wake pipe");
      nonblocking(wake_[0]); nonblocking(wake_[1]);
      worker_ = std::thread([this] { worker_loop(); });
    } catch (...) { close_fds(); throw; }
  }
  ~Impl() {
    { std::lock_guard<std::mutex> lock(mutex_); shutdown_ = true; }
    cv_.notify_one();
    if (worker_.joinable()) worker_.join();
    close_fds();
  }
  uint16_t port() const noexcept { return port_; }
  bool draining() const noexcept { return listener_draining_.load(std::memory_order_relaxed); }
  void run(const std::atomic<bool>& stop, const std::atomic<int>* desired_transport) {
    if (ran_) throw std::logic_error("OPIF UdpServer::run is single-use");
    ran_ = true;
    try {
      while (!stopping(stop, desired_transport)) {
        std::vector<pollfd> descriptors{{fd_, POLLIN, 0}, {wake_[0], POLLIN, 0}, {tcp_fd_, POLLIN, 0}};
        std::vector<uint64_t> connections;
        for (const auto& entry : tcp_) {
          connections.push_back(entry.first);
          descriptors.push_back({entry.second.fd, short(POLLIN | (entry.second.tx.empty() ? 0 : POLLOUT)), 0});
        }
        const int result = poll(descriptors.data(), nfds_t(descriptors.size()), 100);
        if (result < 0 && errno != EINTR) throw std::runtime_error("OPIF socket poll failed");
        if (stopping(stop, desired_transport)) break;
        maintain();
        if (result > 0 && (descriptors[0].revents & (POLLERR | POLLNVAL)))
          throw std::runtime_error("OPIF socket failed");
        if (result > 0 && (descriptors[0].revents & POLLIN)) receive_batch();
        if (result > 0 && (descriptors[2].revents & (POLLERR | POLLHUP | POLLNVAL)))
          throw std::runtime_error("OPIF TCP listener failed");
        if (result > 0 && (descriptors[2].revents & POLLIN)) accept_tcp();
        for (size_t i = 0; i < connections.size(); ++i) {
          auto it = tcp_.find(connections[i]);
          if (it == tcp_.end()) continue;
          const short events = descriptors[i + 3].revents;
          if (events & (POLLERR | POLLNVAL)) it->second.failed = true;
          if (!it->second.failed && (events & (POLLIN | POLLHUP))) receive_tcp(it->second);
        }
        // Observe STOP/EOF before a completed inference can promote the waiting
        // frame. A disconnected owner never intentionally starts its next frame.
        reap_tcp();
        drain_completions(&stop, desired_transport);
        // Include output queued by completions and newly received controls in
        // this iteration, rather than adding one poll interval to each reply.
        for (auto& entry : tcp_) if (!entry.second.failed) flush_tcp(entry.second);
        reap_tcp();
      }
    } catch (...) { drain_runtime(); throw; }
    drain_runtime();
  }

 private:
  enum class Phase { Idle, Pending, Active, Draining };
  enum class Work { Begin, Infer, End };
  struct Job { Work kind; InferenceRequest request; };
  struct Completion { Work kind; uint64_t request_id; InferenceResponse response; std::string error; InferenceRequest request{}; uint32_t queue_us=0; };
  struct Assembly {
    Header header;
    Bytes body, seen;
    size_t received = 0;
    Time updated;
  };
  struct Terminal { uint64_t request_id; std::vector<Bytes> packets; };
  struct Connection {
    int fd;
    Peer peer;
    Bytes rx, tx;
    size_t tx_offset = 0;
    Time last_received = Clock::now(), partial_since{};
    bool failed = false;
  };
  static constexpr size_t kMaximumConnections = 8, kMaximumPendingWrite = 2 * 1024 * 1024;
  static constexpr size_t kStreamBudget = 256 * 1024;

  bool stopping(const std::atomic<bool>& stop, const std::atomic<int>* desired_transport) {
    if (stop.load(std::memory_order_relaxed) ||
        (desired_transport && desired_transport->load(std::memory_order_relaxed) != int(transport_)))
      listener_draining_.store(true, std::memory_order_relaxed);
    return draining();  // A -> B -> A cannot revive an already retiring listener.
  }

  void close_fds() {
    if (fd_ >= 0) close(fd_);
    if (tcp_fd_ >= 0) close(tcp_fd_);
    for (auto& entry : tcp_) close(entry.second.fd);
    tcp_.clear();
    if (wake_[0] >= 0) close(wake_[0]);
    if (wake_[1] >= 0) close(wake_[1]);
  }
  void worker_loop() {
    while (true) {
      Job work;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this] { return shutdown_ || job_.has_value(); });
        if (shutdown_ && !job_) return;
        work = std::move(*job_); job_.reset();
      }
      Completion completion{work.kind, work.request.request_id, {}, {}};
      try {
        if (work.kind == Work::Begin) runtime_.begin_session();
        else if (work.kind == Work::End) runtime_.end_session();
        else {
          const auto started_ns = uptime_ns();
          completion.queue_us = uint32_t(std::min<uint64_t>((started_ns - work.request.admitted_ns) / 1000,
                                                          std::numeric_limits<uint32_t>::max()));
          completion.response = runtime_.infer(work.request);
          if (completion.response.output.size() != kOutputElements)
            throw std::runtime_error("runtime returned wrong Cinque v3 output element count");
          if (!std::all_of(completion.response.output.begin(), completion.response.output.end(),
                           [](float v) { return std::isfinite(v); }))
            throw std::runtime_error("runtime returned nonfinite full output (including hidden)");
          completion.request = std::move(work.request);
        }
      } catch (const std::exception& error) { completion.error = error.what(); }
      catch (...) { completion.error = "unknown accelerator execution failure"; }
      { std::lock_guard<std::mutex> lock(mutex_); completion_ = std::move(completion); }
      const uint8_t byte = 1;
      // Nonblocking wakeups may coalesce; completion_ remains authoritative.
      (void)write(wake_[1], &byte, 1);
    }
  }
  void submit(Work work, InferenceRequest request = {}) {
    if (worker_busy_) throw std::logic_error("OPIF runtime worker over-admission");
    worker_busy_ = true;
    { std::lock_guard<std::mutex> lock(mutex_); job_ = Job{work, std::move(request)}; }
    cv_.notify_one();
  }
  void drain_completions(const std::atomic<bool>* stop = nullptr,
                         const std::atomic<int>* desired_transport = nullptr) {
    uint8_t bytes[64]; while (read(wake_[0], bytes, sizeof(bytes)) > 0) {}
    std::optional<Completion> done;
    { std::lock_guard<std::mutex> lock(mutex_); done = std::move(completion_); completion_.reset(); }
    if (!done) return;
    worker_busy_ = false;
    if (stop && stopping(*stop, desired_transport) &&
        (phase_ == Phase::Pending || phase_ == Phase::Active)) {
      finish_session(); return;
    }
    if (phase_ == Phase::Draining) {
      if (done->kind == Work::End) phase_ = Phase::Idle;
      else submit(Work::End);
      return;
    }
    if (done->kind == Work::Begin && phase_ == Phase::Pending) {
      if (Clock::now() - started_ >= std::chrono::seconds(60)) { finish_session(); return; }
      if (!done->error.empty()) {
        send_error(owner_, handshake_id_, 4, done->error, 0, 0);
        finish_session(); return;
      }
      phase_ = Phase::Active; last_activity_ = Clock::now();
      send_ready(handshake_id_); return;
    }
    if (done->kind != Work::Infer || phase_ != Phase::Active) return;
    in_flight_ = 0;
    Bytes body;
    uint8_t type = Result;
    if (!done->error.empty()) {
      reset_required_ = true; type = Error;
      body = error_body(11, expected_, done->error);
    } else {
      const auto count = output_encoding_ == 2 ? kControlOutputElements : kOutputElements;
      body = Bytes{0, output_encoding_, output_encoding_, 0}; body.reserve(24 + 4 * count);
      put32(body, uint32_t(count)); put32(body, done->response.inference_time_us);
      put32(body, done->queue_us); put64(body, uptime_ns());
      for (size_t i = 0; i < kOutputElements; ++i) {
        if (output_encoding_ == 2 && i >= 2066 && i < 18450) continue;
        const float value = done->response.output[i];
        uint32_t bits; std::memcpy(&bits, &value, sizeof(bits)); put32(body, bits);
      }
    }
    terminal(type, done->request_id, body);
    // Attempt transport delivery before background diagnostics/preview admission.
    if (owner_.connection) {
      auto connection = tcp_.find(owner_.connection);
      if (connection != tcp_.end() && !connection->second.failed) flush_tcp(connection->second);
    }
    if (done->error.empty()) runtime_.result_queued(std::move(done->request), done->response.inference_time_us);
    if (stop && stopping(*stop, desired_transport)) {
      finish_session(); return;
    }
    if (owner_.connection) {
      const auto connection = tcp_.find(owner_.connection);
      if (connection == tcp_.end() || connection->second.failed) {
        finish_session(); return;  // Output backpressure also cancels the queue.
      }
    }
    if (!done->error.empty()) {
      // Both accepted IDs are consumed. The queued input must not advance a
      // recurrent state whose preceding inference failed.
      if (waiting_) {
        const uint64_t cancelled = waiting_->request_id;
        waiting_.reset();
        terminal(Error, cancelled, error_body(11, expected_,
          "queued inference cancelled after prior accelerator failure; next request requires RESET_TEMPORAL"));
      }
    } else if (waiting_) {
      InferenceRequest next = std::move(*waiting_); waiting_.reset();
      in_flight_ = next.request_id;
      submit(Work::Infer, std::move(next));
    }
  }
  void terminal(uint8_t type, uint64_t request, const Bytes& body) {
    terminals_.push_back({request, datagrams(type, session_, request, body, maximum_)});
    if (terminals_.size() > 32) terminals_.pop_front();
    send_packets(owner_, terminals_.back().packets);
  }
  void finish_session() {
    phase_ = Phase::Draining; assemblies_.clear(); terminals_.clear(); ready_.clear();
    waiting_.reset();
    in_flight_ = 0; session_ = 0;
    if (!worker_busy_) submit(Work::End);
  }
  void drain_runtime() {
    listener_draining_.store(true, std::memory_order_relaxed);
    if (phase_ == Phase::Idle) return;
    if (phase_ != Phase::Draining) finish_session();
    while (phase_ != Phase::Idle) {
      pollfd descriptor{wake_[0], POLLIN, 0}; (void)poll(&descriptor, 1, 100);
      drain_completions();
    }
  }
  void maintain() {
    const auto now = Clock::now();
    if ((phase_ == Phase::Pending && now - started_ >= std::chrono::seconds(60)) ||
        (phase_ == Phase::Active && now - last_activity_ >= std::chrono::seconds(5))) {
      finish_session(); return;
    }
    for (auto it = assemblies_.begin(); it != assemblies_.end();) {
      if (now - it->second.updated >= std::chrono::milliseconds(500)) it = assemblies_.erase(it);
      else ++it;
    }
  }
  void accept_tcp() {
    for (size_t attempt = 0; attempt < kMaximumConnections; ++attempt) {
      sockaddr_in address{}; socklen_t size = sizeof(address);
      const int fd = accept(tcp_fd_, reinterpret_cast<sockaddr*>(&address), &size);
      if (fd < 0) { if (errno == EINTR) continue; return; }
      if (tcp_.size() >= kMaximumConnections || next_connection_ == 0) { close(fd); continue; }
      try {
        nonblocking(fd);
        int enabled = 1;
        if (setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &enabled, sizeof(enabled)) != 0)
          throw std::runtime_error("cannot set TCP_NODELAY");
#ifdef SO_NOSIGPIPE
        if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &enabled, sizeof(enabled)) != 0)
          throw std::runtime_error("cannot suppress TCP SIGPIPE");
#endif
        const uint64_t identity = next_connection_++;
        Connection connection{fd, {address, identity}, {}, {}, 0, Clock::now(), {}, false};
        tcp_.emplace(identity, std::move(connection));
      } catch (...) { close(fd); }
    }
  }
  void receive_tcp(Connection& connection) {
    std::array<uint8_t, 32768> incoming{};
    for (size_t received = 0; received < kStreamBudget && !connection.failed;) {
      const ssize_t count = recv(connection.fd, incoming.data(), incoming.size(), 0);
      if (count == 0) { connection.failed = true; return; }
      if (count < 0) {
        if (errno == EINTR) continue;
        if (errno != EAGAIN && errno != EWOULDBLOCK) connection.failed = true;
        return;
      }
      received += size_t(count); connection.last_received = Clock::now();
      const bool had_partial = !connection.rx.empty();
      connection.rx.insert(connection.rx.end(), incoming.begin(), incoming.begin() + count);
      size_t consumed = 0;
      while (connection.rx.size() - consumed >= 4 && !connection.failed) {
        const uint32_t length = u32(connection.rx.data() + consumed);
        if (length < kHeaderBytes || length > kMaximumDatagramBytes) { connection.failed = true; return; }
        if (connection.rx.size() - consumed < size_t(length) + 4) break;
        const uint8_t* packet = connection.rx.data() + consumed + 4;
        Header header;
        if (!decode_header(packet, length, header)) { connection.failed = true; return; }
        receive(connection.peer, header, packet + kHeaderBytes);
        consumed += size_t(length) + 4;
      }
      connection.rx.erase(connection.rx.begin(), connection.rx.begin() + consumed);
      // Every complete packet has been dispatched; unread complete frames remain
      // in the kernel and therefore keep poll readable. User buffering is <=1235.
      if (connection.rx.empty()) connection.partial_since = {};
      else if (!had_partial || consumed) connection.partial_since = Clock::now();
    }
  }
  void flush_tcp(Connection& connection) {
    size_t written = 0;
    while (connection.tx_offset < connection.tx.size() && written < kStreamBudget) {
      int flags = 0;
#ifdef MSG_NOSIGNAL
      flags = MSG_NOSIGNAL;
#endif
      const size_t available = std::min(connection.tx.size() - connection.tx_offset, kStreamBudget - written);
      const ssize_t count = ::send(connection.fd, connection.tx.data() + connection.tx_offset, available, flags);
      if (count < 0) {
        if (errno == EINTR) continue;
        if (errno != EAGAIN && errno != EWOULDBLOCK) connection.failed = true;
        return;
      }
      if (!count) { connection.failed = true; return; }
      connection.tx_offset += size_t(count); written += size_t(count);
    }
    if (connection.tx_offset == connection.tx.size()) { connection.tx.clear(); connection.tx_offset = 0; }
  }
  void reap_tcp() {
    const auto now = Clock::now();
    for (auto it = tcp_.begin(); it != tcp_.end();) {
      const bool owner = same_peer(owner_, it->second.peer) &&
        (phase_ == Phase::Active || phase_ == Phase::Pending);
      const bool stale_partial = !it->second.rx.empty() && now - it->second.partial_since >= std::chrono::seconds(5);
      const bool idle = !owner && now - it->second.last_received >= std::chrono::seconds(10);
      if (!it->second.failed && !stale_partial && !idle) { ++it; continue; }
      close(it->second.fd); it = tcp_.erase(it);
      if (owner) finish_session();  // Worker drains before another transport owns it.
    }
  }
  void queue_tcp(Connection& connection, const Bytes& packet) {
    if (connection.failed) return;
    if (connection.tx.size() - connection.tx_offset + packet.size() + 4 > kMaximumPendingWrite) {
      connection.failed = true; return;
    }
    if (connection.tx_offset) {
      connection.tx.erase(connection.tx.begin(), connection.tx.begin() + connection.tx_offset);
      connection.tx_offset = 0;
    }
    put32(connection.tx, uint32_t(packet.size()));
    connection.tx.insert(connection.tx.end(), packet.begin(), packet.end());
  }
  void send_packets(const Peer& peer, const std::vector<Bytes>& packets) {
    // All fragments append to one contiguous write buffer; flush happens once
    // after dispatch, never one small TCP write per datagram.
    for (const auto& packet : packets) send_packet(peer, packet);
  }
  void send_packet(const Peer& peer, const Bytes& packet) {
    if (peer.connection) {
      const auto it = tcp_.find(peer.connection);
      if (it != tcp_.end()) queue_tcp(it->second, packet);
      return;
    }
    // UDP send failures are recoverable with the existing fragment-repair ABI.
#ifdef __linux__
    alignas(cmsghdr) std::array<uint8_t, CMSG_SPACE(sizeof(in_pktinfo))> control{};
    iovec buffer{const_cast<uint8_t*>(packet.data()), packet.size()};
    msghdr message{};
    message.msg_name = const_cast<sockaddr_in*>(&peer.address);
    message.msg_namelen = sizeof(peer.address);
    message.msg_iov = &buffer; message.msg_iovlen = 1;
    message.msg_control = control.data(); message.msg_controllen = control.size();
    cmsghdr* ancillary = CMSG_FIRSTHDR(&message);
    ancillary->cmsg_level = IPPROTO_IP; ancillary->cmsg_type = IP_PKTINFO;
    ancillary->cmsg_len = CMSG_LEN(sizeof(in_pktinfo));
    in_pktinfo info{};
    info.ipi_ifindex = peer.interface_index;
    info.ipi_spec_dst = peer.local_address;
    std::memcpy(CMSG_DATA(ancillary), &info, sizeof(info));
    (void)sendmsg(fd_, &message, 0);
#else
    (void)sendto(fd_, packet.data(), packet.size(), 0, reinterpret_cast<const sockaddr*>(&peer.address), sizeof(peer.address));
#endif
  }
  void send(const Peer& peer, uint8_t type, uint64_t session,
            uint64_t request, const Bytes& body, uint16_t maximum = kMaximumDatagramBytes) {
    send_packets(peer, datagrams(type, session, request, body, maximum));
  }
  void send_error(const Peer& peer, uint64_t request, uint16_t code,
                  const std::string& message, uint64_t expected = 0,
                  std::optional<uint64_t> session = std::nullopt) {
    send(peer, Error, session.value_or(session_), request, error_body(code, expected, message), kMinimumDatagramBytes);
  }
  void send_status() {
    Bytes body{1, kMaximumInFlight, kMaximumInFlight, 0}; put64(body, 1);
    send(owner_, PipelineStatus, session_, 1, body, maximum_);
  }
  void send_ready(uint64_t request) {
    send(owner_, Ready, session_, request, ready_, maximum_); send_status();
  }
  void accepted(uint64_t request) { send(owner_, Accepted, session_, request, Bytes{Infer}, maximum_); }
  void replay(uint64_t request) {
    for (const auto& cached : terminals_) if (cached.request_id == request) {
      send_packets(owner_, cached.packets); return;
    }
    if ((in_flight_ == request && in_flight_) || (waiting_ && waiting_->request_id == request)) accepted(request);
    else send_error(owner_, request, 12, "terminal response expired from cache", expected_);
  }
  bool canonical(const Header& h) const {
    const size_t limit = maximum_ - kHeaderBytes;
    const size_t count = std::max<size_t>(1, (h.message_bytes + limit - 1) / limit);
    const size_t offset = size_t(h.fragment_index) * limit;
    return h.fragment_count == count && offset <= h.message_bytes &&
      h.payload_bytes == std::min<size_t>(limit, h.message_bytes - offset);
  }
  void receive_batch() {
    // UDP non-owners cannot allocate session or assembly storage. One owner,
    // six assemblies and 32 terminals remain shared with the bounded TCP peers.
    for (unsigned count = 0; count < 128; ++count) {
      std::array<uint8_t, kMaximumDatagramBytes + 1> packet{};
      Peer peer{};
      socklen_t size = sizeof(peer.address);
#ifdef __linux__
      alignas(cmsghdr) std::array<uint8_t, CMSG_SPACE(sizeof(in_pktinfo))> control{};
      iovec buffer{packet.data(), packet.size()};
      msghdr message{};
      message.msg_name = &peer.address; message.msg_namelen = size;
      message.msg_iov = &buffer; message.msg_iovlen = 1;
      message.msg_control = control.data(); message.msg_controllen = control.size();
      const ssize_t length = recvmsg(fd_, &message, 0);
      if (length < 0) { if (errno == EINTR) continue; return; }
      if (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) continue;
      size = message.msg_namelen;
      for (cmsghdr* ancillary = CMSG_FIRSTHDR(&message); ancillary;
           ancillary = CMSG_NXTHDR(&message, ancillary)) {
        if (ancillary->cmsg_level == IPPROTO_IP && ancillary->cmsg_type == IP_PKTINFO &&
            ancillary->cmsg_len == CMSG_LEN(sizeof(in_pktinfo))) {
          in_pktinfo info{};
          std::memcpy(&info, CMSG_DATA(ancillary), sizeof(info));
          peer.interface_index = info.ipi_ifindex;
          peer.local_address = info.ipi_addr;
        }
      }
      // Never silently fall back to the default network if path metadata is lost.
      if (peer.interface_index <= 0 || peer.local_address.s_addr == INADDR_ANY) continue;
#else
      const ssize_t length = recvfrom(fd_, packet.data(), packet.size(), 0,
                                     reinterpret_cast<sockaddr*>(&peer.address), &size);
      if (length < 0) { if (errno == EINTR) continue; return; }
#endif
      Header h;
      if (size != sizeof(peer.address) || !decode_header(packet.data(), size_t(length), h)) continue;
      receive(peer, h, packet.data() + kHeaderBytes);
    }
  }
  void receive(const Peer& peer, const Header& h, const uint8_t* p) {
    const bool single = h.fragment_count == 1 && h.fragment_index == 0 &&
      h.message_bytes == h.payload_bytes && crc32c(p, h.payload_bytes) == h.message_crc32c;
    if (h.type == Discover) {
      if (!single || h.session_id || !h.request_id || h.payload_bytes) return;
      const uint8_t available = phase_ == Phase::Idle ? 0 : phase_ == Phase::Active ? 2 : 1;
      Bytes b{1, available}; put16(b, available == 0 ? 1 : 0); put16(b, port_);
      put16(b, kMaximumDatagramBytes); put16(b, kMinimumDatagramBytes); put16(b, 0);
      put32(b, 5000); put64(b, instance_); send(peer, Announce, 0, h.request_id, b); return;
    }
    if (h.type == Start) { start(peer, h, p, single); return; }
    if (phase_ != Phase::Active && phase_ != Phase::Pending) return;
    if (!same_peer(peer, owner_)) return;
    if (phase_ == Phase::Pending) {
      if (h.session_id && h.session_id != session_) return;
      if (!single) return;
      if (h.type == Ping) send(owner_, Pong, session_, h.request_id, Bytes(p, p + h.payload_bytes), maximum_);
      else if (h.type == Stop && !h.payload_bytes) {
        send(owner_, Stopped, session_, h.request_id, {}, maximum_); finish_session();
      }
      return;
    }
    if (h.session_id != session_ || h.payload_bytes + kHeaderBytes > maximum_) return;
    if (h.type == Infer) {
      if (!canonical(h) || h.message_bytes < 32) return;
      last_activity_ = Clock::now(); fragment(h, p); return;
    }
    if (!single) return;
    if (h.type == Ping) {
      last_activity_ = Clock::now();
      send(owner_, Pong, session_, h.request_id, Bytes(p, p + h.payload_bytes), maximum_); send_status();
    } else if (h.type == Stop && !h.payload_bytes) {
      send(owner_, Stopped, session_, h.request_id, {}, maximum_); finish_session();
    } else if (h.type == Accepted && h.payload_bytes == 1 && p[0] == Result) {
      last_activity_ = Clock::now();
    } else if (h.type == Query) query(h, p);
    else if (h.type == Missing) missing(h, p);
  }
  void start(const Peer& peer, const Header& h, const uint8_t* p, bool single) {
    if (!single || h.session_id || !h.request_id || h.payload_bytes < 12 ||
        p[0] != 0 || p[1] != 0 || (p[2] != 0 && p[2] != 2) || p[3] != 0 || u32(p + 6) != 0 ||
        h.payload_bytes != 12 + u16(p + 10) || !utf8(p + 12, h.payload_bytes - 12)) {
      send_error(peer, h.request_id, 1, "START requires currentPacked6, uncompressed FP32 and valid UTF-8", 0, h.session_id);
      return;
    }
    if (phase_ != Phase::Idle) {
      if ((phase_ == Phase::Active || phase_ == Phase::Pending) && same_peer(peer, owner_)) {
        if (phase_ == Phase::Active) { last_activity_ = Clock::now(); send_ready(h.request_id); }
      } else send_error(peer, h.request_id, 2, "server already has an owner or is draining accelerator work", 0, h.session_id);
      return;
    }
    owner_ = peer; session_ = nonce(); handshake_id_ = h.request_id; expected_ = 1; state_epoch_ = 1; output_encoding_ = p[2];
    maximum_ = std::clamp<uint16_t>(u16(p + 4), kMinimumDatagramBytes, kMaximumDatagramBytes);
    reset_required_ = false; started_ = last_activity_ = Clock::now(); phase_ = Phase::Pending;
    const std::string model = "comma big model cinque v3 / QNN HTP";
    const std::string abi = output_encoding_ == 2 ? std::string("sha256:") + kSourceSHA256 + ";op-supercombo-2068-f32-d33-s4-v2" : kABI;
    ready_ = Bytes{0, 0, 0, output_encoding_}; put16(ready_, maximum_); put16(ready_, 0);
    put32(ready_, kTensorBytes); put32(ready_, output_encoding_ == 2 ? kControlOutputElements : kOutputElements); put32(ready_, 5000);
    put16(ready_, 32); put16(ready_, 33); ready_.push_back(4); ready_.push_back(kMaximumInFlight);
    put16(ready_, uint16_t(model.size())); put16(ready_, uint16_t(abi.size()));
    ready_.insert(ready_.end(), model.begin(), model.end()); ready_.insert(ready_.end(), abi.begin(), abi.end());
    submit(Work::Begin);
  }
  void fragment(const Header& h, const uint8_t* p) {
    if (h.request_id < expected_) { if (!h.fragment_index) replay(h.request_id); return; }
    auto it = assemblies_.find(h.request_id);
    if (it == assemblies_.end()) {
      if (assemblies_.size() == 6) { send_error(owner_, h.request_id, 5, "too many incomplete messages"); return; }
      it = assemblies_.emplace(h.request_id, Assembly{h, Bytes(h.message_bytes), Bytes(h.fragment_count), 0, Clock::now()}).first;
    }
    Assembly& a = it->second;
    const size_t offset = size_t(h.fragment_index) * (maximum_ - kHeaderBytes);
    if (a.header.fragment_count != h.fragment_count || a.header.message_bytes != h.message_bytes ||
        a.header.message_crc32c != h.message_crc32c ||
        (a.seen[h.fragment_index] && std::memcmp(a.body.data() + offset, p, h.payload_bytes))) {
      assemblies_.erase(it); send_error(owner_, h.request_id, 6, "inconsistent fragment metadata or duplicate payload"); return;
    }
    a.updated = Clock::now();
    if (!a.seen[h.fragment_index]) {
      std::copy(p, p + h.payload_bytes, a.body.begin() + offset); a.seen[h.fragment_index] = 1; ++a.received;
    }
    if (a.received != h.fragment_count) return;
    Bytes body = std::move(a.body); assemblies_.erase(it);
    if (crc32c(body.data(), body.size()) != h.message_crc32c) {
      send_error(owner_, h.request_id, 7, "message CRC32C mismatch"); return;
    }
    if (h.request_id != expected_) {
      send_error(owner_, h.request_id, 8, "request sequence gap", expected_); return;
    }
    p = body.data();
    if (body.size() != 32 + kTensorBytes || p[0] || p[1] || p[2] > 7 || p[3] > 1 ||
        (u16(p + 4) & ~1u) || u16(p + 6) || u32(p + 24) != kTensorBytes ||
        u32(p + 28) != kTensorBytes || !std::isfinite(f32(p + 8)) || !std::isfinite(f32(p + 12)) ||
        (reset_required_ && !(u16(p + 4) & 1))) {
      send_error(owner_, h.request_id, 10, "malformed request or RESET_TEMPORAL required", expected_); return;
    }
    if ((u16(p + 4) & 1) && (worker_busy_ || waiting_)) {
      send_error(owner_, h.request_id, 9, "RESET_TEMPORAL requires an empty inference window; retry this request ID", expected_); return;
    }
    if (waiting_) { send_error(owner_, h.request_id, 9, "inference window full; retry this request ID", expected_); return; }
    if (expected_ == std::numeric_limits<uint64_t>::max()) {
      send_error(owner_, h.request_id, 10, "request ID exhausted; start a fresh session", expected_); return;
    }
    InferenceRequest request;
    request.session_id = session_; request.request_id = h.request_id;
    request.client_timestamp_ns = u64(p + 16); request.desire = p[2]; request.traffic_convention = p[3];
    request.reset_temporal = u16(p + 4) & 1; request.action_t = {f32(p + 8), f32(p + 12)};
    request.tensor.assign(p + 32, p + body.size());
    if (request.reset_temporal && h.request_id > 1) ++state_epoch_;
    request.state_epoch = state_epoch_; request.admitted_ns = uptime_ns();
    ++expected_; reset_required_ = false;
    if (worker_busy_) waiting_ = std::move(request);
    else {
      in_flight_ = h.request_id;
      submit(Work::Infer, std::move(request));
    }
    accepted(h.request_id);
  }
  void query(const Header& h, const uint8_t* p) {
    if (h.payload_bytes != 12 || p[1] || (p[0] != Result && p[0] != Infer)) return;
    if (p[0] == Result) { last_activity_ = Clock::now(); replay(h.request_id); return; }
    const uint16_t count = u16(p + 2); const uint32_t bytes = u32(p + 4), crc = u32(p + 8);
    const size_t limit = maximum_ - kHeaderBytes;
    if (bytes < 32 || bytes > kMaximumMessageBytes || count != (bytes + limit - 1) / limit) return;
    last_activity_ = Clock::now();
    if (h.request_id < expected_) { replay(h.request_id); return; }
    const auto it = assemblies_.find(h.request_id);
    const Assembly* a = it != assemblies_.end() && it->second.header.fragment_count == count &&
      it->second.header.message_bytes == bytes && it->second.header.message_crc32c == crc ? &it->second : nullptr;
    Bytes body{Infer, 0}; put16(body, count); body.resize(4 + (count + 7) / 8);
    for (size_t i = 0; i < count; ++i) if (!a || !a->seen[i]) body[4 + i / 8] |= uint8_t(1u << (i % 8));
    send(owner_, Missing, session_, h.request_id, body, maximum_);
  }
  void missing(const Header& h, const uint8_t* p) {
    if (h.payload_bytes < 4 || p[0] != Result || p[1]) return;
    const uint16_t count = u16(p + 2);
    if (!count || h.payload_bytes != 4 + (count + 7) / 8) return;
    for (const auto& cached : terminals_) if (cached.request_id == h.request_id && cached.packets.size() == count) {
      last_activity_ = Clock::now();
      for (size_t i = 0; i < count; ++i) if (p[4 + i / 8] & (1u << (i % 8))) send_packet(owner_, cached.packets[i]);
      return;
    }
  }

  InferenceRuntime& runtime_;
  const Transport transport_;
  std::atomic<bool> listener_draining_{false};
  int fd_ = -1, tcp_fd_ = -1, wake_[2]{-1, -1};
  uint64_t next_connection_ = 1;
  std::map<uint64_t, Connection> tcp_;
  uint16_t port_ = 0, maximum_ = kMaximumDatagramBytes;
  uint64_t instance_, session_ = 0, handshake_id_ = 0, expected_ = 1, in_flight_ = 0, state_epoch_ = 1;
  uint8_t output_encoding_ = 0;
  Peer owner_{};
  Phase phase_ = Phase::Idle;
  Time started_{}, last_activity_{};
  Bytes ready_;
  std::map<uint64_t, Assembly> assemblies_;
  std::deque<Terminal> terminals_;
  std::optional<InferenceRequest> waiting_;
  bool reset_required_ = false, worker_busy_ = false, ran_ = false;
  std::mutex mutex_;
  std::condition_variable cv_;
  std::optional<Job> job_;
  std::optional<Completion> completion_;
  bool shutdown_ = false;
  std::thread worker_;
};

UdpServer::UdpServer(InferenceRuntime& runtime, uint16_t port, Transport transport)
    : impl_(std::make_unique<Impl>(runtime, port, transport)) {}
UdpServer::~UdpServer() = default;
uint16_t UdpServer::port() const noexcept { return impl_->port(); }
bool UdpServer::draining() const noexcept { return impl_->draining(); }
void UdpServer::run(const std::atomic<bool>& stop, const std::atomic<int>* desired_transport) {
  impl_->run(stop, desired_transport);
}
}  // namespace opif
