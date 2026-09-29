#include "qnn_runtime.h"
#include "qnn_context_cache.h"
#include <onnxruntime_cxx_api.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <unordered_map>
#ifdef __ANDROID__
#include <android/log.h>
#include <sys/system_properties.h>
#endif

namespace opif {
namespace {
void ORT_API_CALL runtime_log(void*, OrtLoggingLevel severity, const char* category,
                             const char* log_id, const char* code_location,
                             const char* message) noexcept {
  const char* safe_category = category ? category : "";
  const char* safe_id = log_id ? log_id : "opif-qnn";
  const char* safe_location = code_location ? code_location : "";
  const char* safe_message = message ? message : "";
  std::fprintf(stderr, "[%s][%d][%s] %s: %s\n", safe_id, static_cast<int>(severity),
               safe_category, safe_location, safe_message);
#ifdef __ANDROID__
  int priority = ANDROID_LOG_WARN;
  switch (severity) {
    case ORT_LOGGING_LEVEL_VERBOSE: priority = ANDROID_LOG_VERBOSE; break;
    case ORT_LOGGING_LEVEL_INFO: priority = ANDROID_LOG_INFO; break;
    case ORT_LOGGING_LEVEL_WARNING: priority = ANDROID_LOG_WARN; break;
    case ORT_LOGGING_LEVEL_ERROR: priority = ANDROID_LOG_ERROR; break;
    case ORT_LOGGING_LEVEL_FATAL: priority = ANDROID_LOG_FATAL; break;
  }
  __android_log_print(priority, "OPIF-QNN", "[%s][%s] %s: %s", safe_id,
                      safe_category, safe_location, safe_message);
#endif
}

void startup_log(const std::string& message) {
  std::cerr << message << '\n';
#ifdef __ANDROID__
  __android_log_print(ANDROID_LOG_INFO, "OPIF-QNN", "%s", message.c_str());
#endif
}

using Clock = std::chrono::steady_clock;
int64_t elapsed_ms(Clock::time_point started) {
  return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - started).count();
}

constexpr const char* kSourceSHA = "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4";
constexpr size_t kImageSize = 2 * 6 * 128 * 256;
constexpr size_t kOutputs = 18452;
constexpr std::array<const char*, 7> kInputs{
    "new_img", "desire", "traffic_convention", "action_t", "state_img_q", "state_desire_q", "state_feat_q"};
constexpr std::array<const char*, 4> kOutputNames{
    "outputs", "next_state_img_q", "next_state_desire_q", "next_state_feat_q"};
const std::array<std::vector<int64_t>, 7> kInputShapes{{
    {2,6,128,256}, {8}, {1,2}, {1,2}, {2,5,6,128,256}, {132,1,8}, {128,1,16384}}};
const std::array<std::vector<int64_t>, 4> kOutputShapes{{
    {1,18452}, {2,5,6,128,256}, {132,1,8}, {128,1,16384}}};

template <class T>
Ort::Value tensor(const Ort::MemoryInfo& memory, T* data, size_t count,
                  const std::vector<int64_t>& shape) {
  return Ort::Value::CreateTensor<T>(memory, data, count, shape.data(), shape.size());
}

void verify_signature(Ort::Session& session, bool input) {
  const size_t count = input ? session.GetInputCount() : session.GetOutputCount();
  if (count != (input ? kInputs.size() : kOutputNames.size()))
    throw std::runtime_error("Cinque v3 tensor count mismatch");
  Ort::AllocatorWithDefaultOptions allocator;
  for (size_t i = 0; i < count; ++i) {
    const auto name = input ? session.GetInputNameAllocated(i, allocator)
                            : session.GetOutputNameAllocated(i, allocator);
    const auto* expected = input ? kInputs[i] : kOutputNames[i];
    const auto info = input ? session.GetInputTypeInfo(i) : session.GetOutputTypeInfo(i);
    const auto tensor_info = info.GetTensorTypeAndShapeInfo();
    const auto type = (input ? (i == 0 || i == 4) : i == 1)
        ? ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8 : ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
    if (std::strcmp(name.get(), expected) != 0 || tensor_info.GetElementType() != type ||
        tensor_info.GetShape() != (input ? kInputShapes[i] : kOutputShapes[i]))
      throw std::runtime_error(std::string("Cinque v3 ABI mismatch at ") + expected);
  }
}

void verify_metadata(Ort::Session& session) {
  Ort::AllocatorWithDefaultOptions allocator;
  auto metadata = session.GetModelMetadata();
  for (const auto& pair : std::array<std::pair<const char*, const char*>, 4>{{
       {"openpilot.model_id", "cinque-v3-big"}, {"openpilot.source_sha256", kSourceSHA},
       {"openpilot.abi_version", "1"}, {"openpilot.allow_cpu_fallback", "0"}}}) {
    auto value = metadata.LookupCustomMetadataMapAllocated(pair.first, allocator);
    if (!value || std::strcmp(value.get(), pair.second) != 0)
      throw std::runtime_error(std::string("Model provenance missing/mismatched: ") + pair.first +
                               "; use tools/prepare_model.py");
  }
}
}  // namespace

struct QnnRuntime::Impl {
  // Declaration order ensures sessions die before the environment/plugin.
  Ort::Env env;
  Ort::MemoryInfo memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
  Ort::Session session{nullptr};
  struct State {
    std::vector<uint8_t> image = std::vector<uint8_t>(kImageSize * 5);
    std::vector<float> desire = std::vector<float>(132 * 8);
    std::vector<float> feature = std::vector<float>(128 * 16384);
    void clear() {
      std::fill(image.begin(), image.end(), 0);
      std::fill(desire.begin(), desire.end(), 0);
      std::fill(feature.begin(), feature.end(), 0);
    }
  } state[2];
  unsigned current = 0;
  uint8_t previous_desire = 0;
  bool profile_enabled = false;

  explicit Impl(const QnnConfig& config)
      : env(config.verbose ? ORT_LOGGING_LEVEL_VERBOSE : ORT_LOGGING_LEVEL_WARNING,
            "opif-qnn", runtime_log, nullptr) {
    const auto basename = config.backend.substr(config.backend.find_last_of('/') + 1);
    if (basename != "libQnnHtp.so")
      throw std::runtime_error("Only libQnnHtp.so is permitted; CPU/GPU backends are prohibited");
    env.RegisterExecutionProviderLibrary("QNNExecutionProvider", config.plugin);
    std::vector<Ort::ConstEpDevice> selected;
    for (const auto& device : env.GetEpDevices()) {
      if (std::strcmp(device.EpName(), "QNNExecutionProvider") == 0 &&
          device.Device().Type() == OrtHardwareDeviceType_NPU) {
        selected.push_back(device);
        break;
      }
    }
    if (selected.empty()) throw std::runtime_error("QNN exposes no NPU device; refusing CPU/GPU fallback");
    Ort::SessionOptions options;
    options.SetLogSeverityLevel(config.verbose ? ORT_LOGGING_LEVEL_VERBOSE : ORT_LOGGING_LEVEL_WARNING);
    if (config.verbose)
      Ort::ThrowOnError(Ort::GetApi().SetSessionLogVerbosityLevel(options, 1));
    options.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
    options.SetIntraOpNumThreads(1);
    options.SetInterOpNumThreads(1);
    options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);
    options.AddConfigEntry("session.disable_cpu_ep_fallback", "1");
    options.AddConfigEntry("session.intra_op.allow_spinning", "0");
    options.AddConfigEntry("session.inter_op.allow_spinning", "0");
    const std::unordered_map<std::string, std::string> provider{
        {"backend_path", config.backend}, {"soc_model", "87"}, {"htp_arch", "81"},
        {"offload_graph_io_quantization", "0"}, {"enable_htp_fp16_precision", "1"},
        {"htp_performance_mode", "sustained_high_performance"},
        {"htp_graph_finalization_optimization_mode", "3"}};
    options.AppendExecutionProvider_V2(env, selected, provider);
    if (!config.profile_prefix.empty()) {
      options.EnableProfiling(config.profile_prefix.c_str());
      profile_enabled = true;
    }
    startup_log("Loading full Cinque v3 on QNN HTP V81; CPU fallback disabled");

    std::unique_ptr<context_cache::Store> cache;
    if (!config.cache_dir.empty() && !config.cache_identity.empty()) {
      // Bind the application-verified model/runtime hashes to every graph option
      // here, so a future option edit cannot silently reuse an incompatible graph.
      std::string identity = "opif-qnn-context-v1\nsource=" + std::string(kSourceSHA) +
          "\nabi=cinque-v3-big-1\ncaller=" + config.cache_identity +
          "\nort=" + OrtGetApiBase()->GetVersionString() +
          "\nexecution=sequential\nintra_threads=1\ninter_threads=1\noptimization=extended"
          "\nstrict_npu=1\nintra_spinning=0\ninter_spinning=0\nembed_context=1\n";
      for (const auto& item : std::map<std::string, std::string>(provider.begin(), provider.end()))
        // The APK install path changes between installations. The caller binds
        // actual library bytes; only the backend name belongs in the graph key.
        identity += item.first + "=" + (item.first == "backend_path" ? basename : item.second) + "\n";
#ifdef __ANDROID__
      for (const char* name : {"ro.vendor.build.fingerprint", "ro.bootimage.build.fingerprint"}) {
        std::string value;
        if (const prop_info* property = __system_property_find(name)) {
          __system_property_read_callback(property,
              [](void* target, const char*, const char* text, uint32_t) {
                *static_cast<std::string*>(target) = text;
              }, &value);
        }
        identity += std::string(name) + "=" + value + "\n";
      }
#endif
      try { cache = std::make_unique<context_cache::Store>(config.cache_dir, identity); }
      catch (const std::exception& error) { startup_log(std::string("QNN_CACHE_UNAVAILABLE ") + error.what()); }
    }

    auto load_session = [&](const std::string& path, const std::string& generated, const char* mode) {
      auto current_options = options.Clone();
      // Generation is explicit and loading never writes another context. The
      // embedded format keeps the ONNX wrapper and compiled HTP binary atomic.
      current_options.AddConfigEntry("ep.context_enable", generated.empty() ? "0" : "1");
      if (!generated.empty()) {
        current_options.AddConfigEntry("ep.context_embed_mode", "1");
        current_options.AddConfigEntry("ep.context_file_path", generated.c_str());
      }
      const auto started = Clock::now();
      session = Ort::Session(env, path.c_str(), current_options);
      startup_log(std::string("QNN_SESSION_READY mode=") + mode + " create_ms=" + std::to_string(elapsed_ms(started)));
    };
    auto verify_abi = [&] {
      verify_signature(session, true);
      verify_signature(session, false);
    };

    if (cache) {
      try {
        const auto path = cache->load();
        if (!path.empty()) {
          load_session(path, {}, "cache");
          verify_abi();
          // EPContext metadata can differ from the source ONNX metadata. Its
          // provenance is the committed manifest: only a source model that passed
          // verify_metadata + ABI + HTP warmup can create that exact hashed blob.
          warmup();
          startup_log("QNN_CACHE_HIT key=" + cache->key());
          return;
        }
        startup_log("QNN_CACHE_MISS key=" + cache->key());
      } catch (const std::exception& error) {
        startup_log(std::string("QNN_CACHE_REJECTED ") + error.what());
        session = Ort::Session{nullptr};
        reset();
        try { cache->invalidate(); }
        catch (const std::exception& cleanup_error) {
          startup_log(std::string("QNN_CACHE_UNAVAILABLE ") + cleanup_error.what());
          cache.reset();
        }
      }
    }

    bool generated = false;
    if (cache) {
      try {
        const auto path = cache->begin();
        load_session(config.model, path, "compile");
        generated = true;
      } catch (const std::exception& error) {
        // An unsupported serializer/full cache filesystem must not disable the
        // server. The retry uses precisely the same HTP-only execution options.
        startup_log(std::string("QNN_CACHE_GENERATION_FAILED ") + error.what());
        session = Ort::Session{nullptr};
        cache.reset();
      }
    }
    if (!generated) load_session(config.model, {}, "source");
    verify_abi();
    verify_metadata(session);
    warmup();
    if (generated) {
      try {
        cache->commit();
        startup_log("QNN_CACHE_SAVED key=" + cache->key());
      } catch (const std::exception& error) {
        // The already initialized model remains usable if only persistence fails.
        startup_log(std::string("QNN_CACHE_SAVE_FAILED ") + error.what());
      }
    }
  }

  void warmup() {
    reset();
    InferenceRequest request{};
    request.tensor.resize(kImageSize);
    request.action_t = {0.4f, 0.7f};
    const auto started = Clock::now();
    execute(request);
    const auto duration = elapsed_ms(started);
    reset();
    startup_log("NPU_WARMUP_OK full graph; no CPU/GPU execution provider fallback; warmup_ms=" +
                std::to_string(duration));
  }

  void reset() noexcept {
    current = 0;
    previous_desire = 0;
    state[0].clear();
    state[1].clear();
  }

  InferenceResponse execute(const InferenceRequest& request) {
    if (request.tensor.size() != kImageSize || request.desire > 7 || request.traffic_convention > 1 ||
        !std::isfinite(request.action_t[0]) || !std::isfinite(request.action_t[1]))
      throw std::runtime_error("Invalid Cinque v3 inference input");
    if (request.reset_temporal) reset();
    std::array<float, 8> pulse{};
    if (request.desire && request.desire != previous_desire) pulse[request.desire] = 1.0f;
    std::array<float, 2> traffic{request.traffic_convention == 0 ? 1.0f : 0.0f,
                                 request.traffic_convention == 1 ? 1.0f : 0.0f};
    auto action = request.action_t;
    auto& before = state[current];
    auto& after = state[1 - current];
    std::array<Ort::Value, 7> inputs{
        tensor(memory, const_cast<uint8_t*>(request.tensor.data()), request.tensor.size(), kInputShapes[0]),
        tensor(memory, pulse.data(), pulse.size(), kInputShapes[1]),
        tensor(memory, traffic.data(), traffic.size(), kInputShapes[2]),
        tensor(memory, action.data(), action.size(), kInputShapes[3]),
        tensor(memory, before.image.data(), before.image.size(), kInputShapes[4]),
        tensor(memory, before.desire.data(), before.desire.size(), kInputShapes[5]),
        tensor(memory, before.feature.data(), before.feature.size(), kInputShapes[6])};
    InferenceResponse response;
    response.output.resize(kOutputs);
    std::array<Ort::Value, 4> outputs{
        tensor(memory, response.output.data(), response.output.size(), kOutputShapes[0]),
        tensor(memory, after.image.data(), after.image.size(), kOutputShapes[1]),
        tensor(memory, after.desire.data(), after.desire.size(), kOutputShapes[2]),
        tensor(memory, after.feature.data(), after.feature.size(), kOutputShapes[3])};
    const auto started = std::chrono::steady_clock::now();
    session.Run(Ort::RunOptions{nullptr}, kInputs.data(), inputs.data(), inputs.size(),
                kOutputNames.data(), outputs.data(), outputs.size());
    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    response.inference_time_us = static_cast<uint32_t>(std::min<int64_t>(elapsed, UINT32_MAX));
    for (float value : response.output) {
      if (!std::isfinite(value)) throw std::runtime_error("NPU produced non-finite output");
    }
    // State advancement happened inside the NPU graph. Only exchange buffer ownership here.
    current = 1 - current;
    previous_desire = request.desire;
    return response;
  }
};

QnnRuntime::QnnRuntime(const QnnConfig& config) : impl_(std::make_unique<Impl>(config)) {}
QnnRuntime::~QnnRuntime() = default;
void QnnRuntime::begin_session() { impl_->reset(); }
void QnnRuntime::end_session() noexcept { impl_->reset(); }
InferenceResponse QnnRuntime::infer(const InferenceRequest& request) {
  try { return impl_->execute(request); }
  catch (...) { impl_->reset(); throw; }
}
std::string QnnRuntime::finish_profile() {
  if (!impl_->profile_enabled) return {};
  Ort::AllocatorWithDefaultOptions allocator;
  auto path = impl_->session.EndProfilingAllocated(allocator);
  impl_->profile_enabled = false;
  return path ? path.get() : "";
}
}  // namespace opif
