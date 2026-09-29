#pragma once

#include "opif_protocol.h"
#include <memory>
#include <string>

namespace opif {
struct QnnConfig {
  std::string model;
  std::string plugin = "libonnxruntime_providers_qnn.so";
  std::string backend = "libQnnHtp.so";
  std::string profile_prefix;
  // Optional dedicated app-private cache directory. The caller must verify the
  // model and bind cache_identity to its deployment SHA, runtime library hashes,
  // and Android build/driver identity before enabling caching.
  std::string cache_dir;
  std::string cache_identity;
  bool verbose = false;
};

// Executes the complete Cinque graph, including its recurrent queue operations.
// Host memory holds the graph's state I/O; the host never computes model layers.
class QnnRuntime final : public InferenceRuntime {
 public:
  explicit QnnRuntime(const QnnConfig& config);
  ~QnnRuntime() override;
  void begin_session() override;
  InferenceResponse infer(const InferenceRequest& request) override;
  void end_session() noexcept override;
  std::string finish_profile();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace opif
