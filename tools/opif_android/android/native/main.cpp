#include "qnn_runtime.h"
#include <atomic>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef __ANDROID__
#include <sys/system_properties.h>
#endif

namespace {
std::atomic<bool> stopped{false};
static_assert(std::atomic<bool>::is_always_lock_free, "signal handler needs lock-free stop flag");
void stop_signal(int) { stopped.store(true, std::memory_order_relaxed); }

unsigned number(const std::string& value, unsigned limit) {
  size_t used = 0;
  const auto result = std::stoul(value, &used);
  if (value.empty() || value[0] == '-' || used != value.size() || result == 0 || result > limit)
    throw std::runtime_error("Invalid positive integer: " + value);
  return static_cast<unsigned>(result);
}

void verify_device() {
#ifdef __ANDROID__
  char soc[PROP_VALUE_MAX]{};
  __system_property_get("ro.soc.model", soc);
  if (std::string(soc).find("SM8850") != 0)
    throw std::runtime_error(std::string("This build targets SM8850 (8 Elite Gen 5), ro.soc.model=") + soc);
#else
  throw std::runtime_error("The NPU server requires Android arm64 on Snapdragon SM8850");
#endif
}

void benchmark(opif::QnnRuntime& runtime, unsigned count,
               const std::string& input_path, const std::string& output_path) {
  std::ifstream input(input_path, std::ios::binary);
  if (!input) throw std::runtime_error("Cannot open packed6 benchmark input: " + input_path);
  input.seekg(0, std::ios::end);
  const auto bytes = input.tellg();
  constexpr size_t frame_size = 393216;
  if (bytes <= 0 || bytes % frame_size != 0)
    throw std::runtime_error("Benchmark input must contain complete 393216-byte packed6 frames");
  input.seekg(0);
  std::ofstream output;
  if (!output_path.empty()) {
    std::error_code alias_error;
    if (input_path == output_path || std::filesystem::equivalent(input_path, output_path, alias_error))
      throw std::runtime_error("Benchmark input and output must differ");
    output.open(output_path, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("Cannot create benchmark output");
  }
  opif::InferenceRequest request{};
  request.tensor.resize(frame_size);
  request.action_t = {0.4f, 0.7f};
  runtime.begin_session();
  uint64_t total_us = 0;
  unsigned completed = 0;
  for (unsigned i = 0; i < count && !stopped.load(); ++i) {
    if (input.peek() == std::char_traits<char>::eof()) {
      input.clear();
      input.seekg(0);
    }
    input.read(reinterpret_cast<char*>(request.tensor.data()), frame_size);
    if (!input) throw std::runtime_error("Failed reading benchmark frame");
    request.request_id = i + 1;
    request.reset_temporal = i == 0;
    const auto response = runtime.infer(request);
    total_us += response.inference_time_us;
    ++completed;
    if (output.is_open()) {
      output.write(reinterpret_cast<const char*>(response.output.data()),
                   static_cast<std::streamsize>(response.output.size() * sizeof(float)));
      if (!output) throw std::runtime_error("Failed writing benchmark output");
    }
    std::cout << "frame=" << i << " inference_us=" << response.inference_time_us << '\n';
  }
  runtime.end_session();
  std::cout << "BENCHMARK frames=" << completed << " mean_inference_us="
            << (completed ? static_cast<double>(total_us) / completed : 0) << '\n';
}
}  // namespace

int main(int argc, char** argv) {
  try {
    opif::QnnConfig config;
    unsigned port = 5555, iterations = 0;
    bool validate_only = false;
    std::string input, output;
    for (int i = 1; i < argc; ++i) {
      const std::string flag = argv[i];
      if (flag == "--help") {
        std::cout << "opif-server --model model.onnx [--port 5555]\n"
                     "  --qnn-library PATH   QNN EP plugin library\n"
                     "  --backend PATH       libQnnHtp.so only\n"
                     "  --profile PREFIX     write ORT provider trace on normal exit\n"
                     "  --verbose            log detailed ORT/QNN node validation diagnostics\n"
                     "  --validate-only      load full NPU graph, run warmup, exit\n"
                     "  --benchmark N --benchmark-input FILE [--benchmark-output FILE]\n"
                     "Benchmark input: concatenated 393216-byte frames; desire=0, LHD, action_t=[0.4,0.7].\n"
                     "No CPU/GPU fallback option exists. Network and buffer management use CPU.\n";
        return 0;
      }
      if (flag == "--validate-only") { validate_only = true; continue; }
      if (flag == "--verbose") { config.verbose = true; continue; }
      if (++i >= argc) throw std::runtime_error("Missing argument for " + flag);
      const std::string value = argv[i];
      if (flag == "--model") config.model = value;
      else if (flag == "--qnn-library") config.plugin = value;
      else if (flag == "--backend") config.backend = value;
      else if (flag == "--profile") config.profile_prefix = value;
      else if (flag == "--port") port = number(value, 65535);
      else if (flag == "--benchmark") iterations = number(value, 1000000);
      else if (flag == "--benchmark-input") input = value;
      else if (flag == "--benchmark-output") output = value;
      else throw std::runtime_error("Unknown option: " + flag);
    }
    if (config.model.empty()) throw std::runtime_error("--model is required");
    if ((iterations != 0) != !input.empty() || (!output.empty() && !iterations) ||
        (validate_only && iterations))
      throw std::runtime_error("Use --benchmark N with --benchmark-input, separately from --validate-only");
    verify_device();
    std::signal(SIGINT, stop_signal);
    std::signal(SIGTERM, stop_signal);
    // Compile/load and warm up before opening UDP. A slow compile cannot consume a session lease.
    opif::QnnRuntime runtime(config);
    if (iterations) benchmark(runtime, iterations, input, output);
    else if (!validate_only) {
      opif::UdpServer server(runtime, static_cast<uint16_t>(port));
      std::cout << "READY OPIF UDP " << server.port()
                << " model=cinque-v3-big backend=HTP-V81 depth=1" << std::endl;
      server.run(stopped);
    }
    const auto profile = runtime.finish_profile();
    if (!profile.empty()) std::cout << "PROFILE " << profile << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FATAL: " << error.what() << '\n';
    return 1;
  }
}
