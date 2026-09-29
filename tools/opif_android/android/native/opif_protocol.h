#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

// OPIF v1 transport only. Model execution and temporal tensors belong to the
// runtime. There is deliberately no CPU/GPU inference implementation here.
namespace opif {
using Bytes = std::vector<uint8_t>;
constexpr size_t kHeaderBytes = 40;
constexpr size_t kTensorBytes = 393216;
constexpr size_t kOutputElements = 18452;
constexpr size_t kControlOutputElements = 2068;
constexpr uint8_t kMaximumInFlight = 2;  // One executing + one waiting; one NPU worker.
constexpr size_t kMaximumMessageBytes = 1048576;
constexpr uint16_t kMaximumDatagramBytes = 1232;
constexpr uint16_t kMinimumDatagramBytes = 512;
inline constexpr const char* kSourceSHA256 =
    "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4";
inline constexpr const char* kABI =
    "sha256:404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4;"
    "op-supercombo-18452-f32-d33-s4-v1";

struct InferenceRequest {
  uint64_t session_id = 0, request_id = 0, client_timestamp_ns = 0;
  uint64_t state_epoch = 1, admitted_ns = 0;
  uint8_t desire = 0, traffic_convention = 0;
  bool reset_temporal = false;
  // Exact finite modeld values; transport never adds a delay or changes units.
  std::array<float, 2> action_t{};
  // img.current followed by big_img.current, each uint8[6][128][256].
  Bytes tensor;
};
struct InferenceResponse {
  std::vector<float> output;
  uint32_t inference_time_us = 0;
};
class InferenceRuntime {
 public:
  virtual ~InferenceRuntime() = default;
  // All three methods run serially on one worker, never on the socket loop.
  // Depth 2 permits one additional accepted request to wait without touching
  // temporal state; infer/reset order always follows accepted request IDs.
  // begin_session must reset all state and prepare/warm the real accelerator.
  // Throwing rejects START. infer must honor reset_temporal before execution;
  // throwing produces terminal code 11 and requires RESET on the next ID.
  virtual void begin_session() = 0;
  virtual InferenceResponse infer(const InferenceRequest&) = 0;
  virtual void end_session() noexcept = 0;
  // Called after terminal reply is queued/flushed. Must not block. Moving the
  // existing input buffer avoids allocating/copying video on the response path.
  virtual void result_queued(InferenceRequest&&, uint32_t) noexcept {}
};

struct Header {
  uint8_t type = 0;
  uint16_t payload_bytes = 0;
  uint64_t session_id = 0, request_id = 0;
  uint16_t fragment_index = 0, fragment_count = 0;
  uint32_t message_bytes = 0, message_crc32c = 0;
};
uint32_t crc32c(const uint8_t* data, size_t size);
bool decode_header(const uint8_t* data, size_t size, Header& header);
std::vector<Bytes> datagrams(uint8_t type, uint64_t session_id,
                             uint64_t request_id, const Bytes& body,
                             uint16_t maximum_datagram_bytes);

enum class Transport : int { Udp = 1, Tcp = 2, Both = 3 };

class UdpServer {
 public:
  // Selected IPv4 wildcard listeners, sharing a port when Both is selected. The historical class
  // name is retained for API compatibility. TCP carries unchanged OPIF datagrams
  // with a uint32 little-endian length prefix; this is an OPIF-over-TCP adapter,
  // not a change to the OPIF v1 wire standard. Both share one owner/worker.
  // Use an isolated USB/hotspot/trusted LAN: ownership is not cryptographic.
  // A zero port asks the OS for an ephemeral port (useful in integration tests).
  explicit UdpServer(InferenceRuntime& runtime, uint16_t port = 5555,
                     Transport transport = Transport::Both);
  ~UdpServer();
  UdpServer(const UdpServer&) = delete;
  UdpServer& operator=(const UdpServer&) = delete;
  uint16_t port() const noexcept;
  // Sticky once run decides to exit, including transport changes and exceptions.
  // Normal client STOP/session expiration does not retire this listener.
  bool draining() const noexcept;
  // Run once; poll observes stop within 100ms. In-progress accelerator work is
  // drained before return, never abandoned while its runtime buffers are used.
  // A changed desired_transport also drains and returns, allowing the caller to
  // destroy this listener and construct another while retaining the runtime.
  void run(const std::atomic<bool>& stop,
           const std::atomic<int>* desired_transport = nullptr);

 private:
  class Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace opif
