#include "qnn_runtime.h"
#include "preview.h"

#include <jni.h>
#include <android/log.h>
#include <sys/system_properties.h>

#include <algorithm>
#include <atomic>
#include <array>
#include <chrono>
#include <ctime>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <thread>
#include <condition_variable>
#include <optional>
#include <stdexcept>
#include <string>

// Java contract, package com.example.openpilotinference.android:
//   static native long createRun();
//   static native void setTransport(long token, int mode);
//   static native void run(long token, String modelPath, String nativeLibDir,
//                          String cacheDir, String cacheIdentity, Callback callback);
//   static native void requestStop(long token);
//   static native void releaseRun(long token);
//   static native void setPreviewEnabled(boolean enabled);
//   static native void renderPreview(byte[] packed, int[] pixels);
// Callback has onState(String,String,int), onStats(boolean,long,double),
// onPreview(byte[],requestId,sessionId,epoch,eofNs), and onPerformance(double[],long[]).
// renderPreview runs on the Java preview worker.
// Create the token before scheduling run(), stop it whenever cancellation is
// requested, and release it in the worker's finally block. In particular, do not
// omit run/release merely because the Java executor's work was cancelled.
namespace {
constexpr const char* kLogTag = "OpenPilotNPU";
using Clock = std::chrono::steady_clock;
constexpr size_t kPerformanceSamples = 256;

struct RunContext {
  std::atomic<bool> stop{false};
  std::atomic<bool> started{false};
  std::atomic<int> desired_transport{3};
};

const char* transport_name(int mode) noexcept {
  switch (mode) {
    case 1: return "UDP";
    case 2: return "TCP";
    case 3: return "TCP/UDP";
    default: return "invalid";
  }
}

bool listener_current(const RunContext& context, int mode) noexcept {
  return !context.stop.load(std::memory_order_acquire) &&
         context.desired_transport.load(std::memory_order_acquire) == mode;
}
std::mutex contexts_mutex;
std::map<jlong, std::shared_ptr<RunContext>> contexts;
jlong next_token = 1;
// QNN initialization and ADSP_LIBRARY_PATH are process resources. Never overlap
// model lifetimes, even if a Java caller releases a running token too early.
std::mutex active_run_mutex;
// Low bit enables preview; remaining bits identify a toggle generation. A
// disable/re-enable during copying invalidates the old frame before delivery.
std::atomic<uint64_t> preview_control{0};
static_assert(opif::preview::kPackedBytes == opif::kTensorBytes);

void set_preview_enabled(bool enabled) noexcept {
  auto previous = preview_control.load(std::memory_order_acquire);
  while (static_cast<bool>(previous & 1) != enabled) {
    const uint64_t next = ((previous + 2) & ~uint64_t{1}) | static_cast<uint64_t>(enabled);
    if (preview_control.compare_exchange_weak(previous, next, std::memory_order_acq_rel)) {
      __android_log_print(ANDROID_LOG_INFO, kLogTag, "preview_enabled=%s", enabled ? "true" : "false");
      return;
    }
  }
}

void disable_failed_preview(uint64_t generation, const char* reason) noexcept {
  const auto disabled = (generation + 2) & ~uint64_t{1};
  if (preview_control.compare_exchange_strong(generation, disabled, std::memory_order_acq_rel)) {
    __android_log_print(ANDROID_LOG_WARN, kLogTag, "Preview disabled: %s; NPU inference continues", reason);
    __android_log_write(ANDROID_LOG_INFO, kLogTag, "preview_enabled=false");
  }
}

void throw_java(JNIEnv* env, const char* type, const std::string& message) {
  if (env->ExceptionCheck()) return;
  jclass error = env->FindClass(type);
  if (!error) return;
  env->ThrowNew(error, message.c_str());
  env->DeleteLocalRef(error);
}

std::shared_ptr<RunContext> find_context(jlong token) {
  std::lock_guard<std::mutex> lock(contexts_mutex);
  const auto found = contexts.find(token);
  return found == contexts.end() ? nullptr : found->second;
}

std::string java_string(JNIEnv* env, jstring value, const char* name, bool absolute_path = true) {
  if (!value) throw std::invalid_argument(std::string(name) + " is required");
  const char* text = env->GetStringUTFChars(value, nullptr);
  if (!text) throw std::runtime_error(std::string("Cannot read ") + name);
  std::string result;
  try { result = text; }
  catch (...) { env->ReleaseStringUTFChars(value, text); throw; }
  env->ReleaseStringUTFChars(value, text);
  if (result.empty() || (absolute_path && result[0] != '/'))
    throw std::invalid_argument(std::string(name) + (absolute_path ? " must be an absolute path" : " is empty"));
  return result;
}

class ThreadEnv {
 public:
  explicit ThreadEnv(JavaVM* vm) : vm_(vm) {
    const jint status = vm_->GetEnv(reinterpret_cast<void**>(&env_), JNI_VERSION_1_6);
    if (status == JNI_EDETACHED) {
      env_ = nullptr;
      attached_ = vm_->AttachCurrentThread(&env_, nullptr) == JNI_OK;
    } else if (status != JNI_OK) env_ = nullptr;
  }
  ~ThreadEnv() { if (attached_) vm_->DetachCurrentThread(); }
  JNIEnv* get() const { return env_; }
 private:
  JavaVM* vm_;
  JNIEnv* env_ = nullptr;
  bool attached_ = false;
};

class Callback {
 public:
  Callback(JNIEnv* env, jobject callback, std::shared_ptr<RunContext> context)
      : context_(std::move(context)) {
    if (!callback) throw std::invalid_argument("Native callback is required");
    if (env->GetJavaVM(&vm_) != JNI_OK) throw std::runtime_error("Cannot obtain Java VM");
    jclass type = env->GetObjectClass(callback);
    if (!type) throw std::runtime_error("Cannot inspect callback");
    state_method_ = env->GetMethodID(type, "onState", "(Ljava/lang/String;Ljava/lang/String;I)V");
    if (!env->ExceptionCheck()) stats_method_ = env->GetMethodID(type, "onStats", "(ZJD)V");
    if (!env->ExceptionCheck()) preview_method_ = env->GetMethodID(type, "onPreview", "([BJJJJ)V");
    if (!env->ExceptionCheck()) performance_method_ = env->GetMethodID(type, "onPerformance", "([D[J)V");
    env->DeleteLocalRef(type);
    if (!state_method_ || !stats_method_ || !preview_method_ || !performance_method_ || env->ExceptionCheck())
      throw std::runtime_error("Callback requires onState(String,String,int), onStats, onPreview(byte[],requestId,sessionId,epoch,eofNs), and onPerformance(double[],long[])");
    jbyteArray staging = env->NewByteArray(static_cast<jsize>(opif::preview::kPackedBytes));
    if (!staging) throw std::runtime_error("Cannot allocate bounded preview staging buffer");
    preview_bytes_ = static_cast<jbyteArray>(env->NewGlobalRef(staging));
    env->DeleteLocalRef(staging);
    object_ = env->NewGlobalRef(callback);
    if (!object_) throw std::runtime_error("Cannot retain native callback");
  }
  ~Callback() {
    ThreadEnv thread(vm_);
    if (auto* env = thread.get()) { env->DeleteGlobalRef(object_); env->DeleteGlobalRef(preview_bytes_); }
  }
  Callback(const Callback&) = delete;
  Callback& operator=(const Callback&) = delete;

  void state(const char* state, const std::string& detail, int listening_transport = 0) noexcept {
    if (listening_transport && !listener_current(*context_, listening_transport)) return;
    __android_log_print(std::strcmp(state, "error") == 0 ? ANDROID_LOG_ERROR : ANDROID_LOG_INFO,
                        kLogTag, "state=%s listening_transport=%d %s", state, listening_transport, detail.c_str());
    ThreadEnv thread(vm_);
    JNIEnv* env = thread.get();
    if (!env) { context_->stop = true; return; }
    // QNN/ORT diagnostic text is UTF-8. ASCII replacement of non-ASCII bytes
    // avoids passing arbitrary SDK diagnostics as JNI's modified UTF-8.
    std::string safe;
    try {
      safe.reserve(detail.size());
      for (unsigned char c : detail) safe.push_back(c < 128 && c ? char(c) : '?');
    } catch (...) { context_->stop = true; return; }
    jstring java_state = env->NewStringUTF(state);
    jstring java_detail = java_state ? env->NewStringUTF(safe.c_str()) : nullptr;
    if (java_state && java_detail && (!listening_transport || listener_current(*context_, listening_transport)))
      env->CallVoidMethod(object_, state_method_, java_state, java_detail, static_cast<jint>(listening_transport));
    if (java_state) env->DeleteLocalRef(java_state);
    if (java_detail) env->DeleteLocalRef(java_detail);
    callback_exception(env);
  }
  void stats(bool connected, uint64_t frames, double milliseconds, int listening_transport = 0) noexcept {
    if (connected && !listener_current(*context_, listening_transport)) return;
    ThreadEnv thread(vm_);
    JNIEnv* env = thread.get();
    if (!env) { context_->stop = true; return; }
    if (!connected || listener_current(*context_, listening_transport))
      env->CallVoidMethod(object_, stats_method_, connected ? JNI_TRUE : JNI_FALSE,
                         static_cast<jlong>(frames), static_cast<jdouble>(milliseconds));
    callback_exception(env);
  }
  void preview(const opif::InferenceRequest& request, Clock::time_point now, int listening_transport) noexcept {
    const auto generation = preview_control.load(std::memory_order_acquire);
    // All successful inference callbacks run serially on the protocol worker.
    // Disabled preview performs no allocation, frame copy, or JNI invocation.
    if (!(generation & 1) || !listener_current(*context_, listening_transport) ||
        now - last_preview_ < std::chrono::milliseconds(100)) return;
    last_preview_ = now;
    if (request.tensor.size() != opif::preview::kPackedBytes) {
      disable_failed_preview(generation, "unexpected packed frame size");
      return;
    }
    ThreadEnv thread(vm_);
    JNIEnv* env = thread.get();
    if (!env) {
      disable_failed_preview(generation, "cannot attach preview callback thread");
      return;
    }
    jbyteArray packed = preview_bytes_; // single background consumer; Java copies into its fixed ring before returning
    if (packed && !env->ExceptionCheck())
      env->SetByteArrayRegion(packed, 0, static_cast<jsize>(request.tensor.size()),
                             reinterpret_cast<const jbyte*>(request.tensor.data()));
    if (packed && !env->ExceptionCheck() &&
        preview_control.load(std::memory_order_acquire) == generation &&
        listener_current(*context_, listening_transport)) {
      last_preview_ = Clock::now();
      env->CallVoidMethod(object_, preview_method_, packed, static_cast<jlong>(request.request_id),
                         static_cast<jlong>(request.session_id), static_cast<jlong>(request.state_epoch),
                         static_cast<jlong>(request.client_timestamp_ns));
    }
    const bool failed = !packed || env->ExceptionCheck();
    if (env->ExceptionCheck()) env->ExceptionClear();

    if (failed) disable_failed_preview(generation, "Java frame allocation or callback failed");
  }
  void performance(const std::array<double, kPerformanceSamples>& milliseconds,
                   const std::array<jlong, kPerformanceSamples>& completion_ns,
                   size_t start, size_t count, int listening_transport) noexcept {
    if (performance_failed_ || !listener_current(*context_, listening_transport)) return;
    ThreadEnv thread(vm_);
    JNIEnv* env = thread.get();
    if (!env) {
      performance_failed_ = true;
      __android_log_write(ANDROID_LOG_WARN, kLogTag,
                          "Performance callbacks disabled: thread attachment failed; NPU inference continues");
      return;
    }
    auto values = env->NewDoubleArray(static_cast<jsize>(count));
    auto times = values && !env->ExceptionCheck() ? env->NewLongArray(static_cast<jsize>(count)) : nullptr;
    if (values && times && !env->ExceptionCheck()) {
      const size_t first = std::min(count, kPerformanceSamples - start);
      // Preserve chronological order across ring wrap without sorting or
      // allocating another native snapshot. Only these two small Java arrays
      // are allocated, at most twice per second.
      env->SetDoubleArrayRegion(values, 0, static_cast<jsize>(first), milliseconds.data() + start);
      if (!env->ExceptionCheck())
        env->SetLongArrayRegion(times, 0, static_cast<jsize>(first), completion_ns.data() + start);
      if (first < count && !env->ExceptionCheck()) {
        env->SetDoubleArrayRegion(values, static_cast<jsize>(first), static_cast<jsize>(count - first), milliseconds.data());
        if (!env->ExceptionCheck())
          env->SetLongArrayRegion(times, static_cast<jsize>(first), static_cast<jsize>(count - first), completion_ns.data());
      }
      if (!env->ExceptionCheck() && listener_current(*context_, listening_transport))
        env->CallVoidMethod(object_, performance_method_, values, times);
    }
    const bool failed = !values || !times || env->ExceptionCheck();
    if (env->ExceptionCheck()) env->ExceptionClear();
    if (values) env->DeleteLocalRef(values);
    if (times) env->DeleteLocalRef(times);
    if (failed) {
      performance_failed_ = true;
      __android_log_write(ANDROID_LOG_WARN, kLogTag,
                          "Performance callbacks disabled: Java allocation or callback failed; NPU inference continues");
    }
  }
 private:
  void callback_exception(JNIEnv* env) noexcept {
    if (!env->ExceptionCheck()) return;
    // A Java UI failure must not escape on an attached inference thread or
    // leave the native model running without a functioning owner/controller.
    env->ExceptionClear();
    context_->stop = true;
    __android_log_write(ANDROID_LOG_ERROR, kLogTag, "Java native callback threw; stopping NPU server");
  }
  JavaVM* vm_ = nullptr;
  jobject object_ = nullptr;
  jbyteArray preview_bytes_ = nullptr;
  jmethodID state_method_ = nullptr, stats_method_ = nullptr, preview_method_ = nullptr;
  jmethodID performance_method_ = nullptr;
  std::shared_ptr<RunContext> context_;
  Clock::time_point last_preview_{};
  bool performance_failed_ = false;
};

class DspEnvironment {
 public:
  explicit DspEnvironment(const std::string& directory) {
    if (directory.find(';') != std::string::npos)
      throw std::invalid_argument("Native library directory contains a DSP path separator");
    if (const char* previous = std::getenv("ADSP_LIBRARY_PATH")) {
      previous_ = previous; had_previous_ = true;
    }
    const std::string path = directory +
      ";/vendor/lib/rfsa/adsp;/vendor/dsp/cdsp;/vendor/dsp;/system/lib/rfsa/adsp";
    if (setenv("ADSP_LIBRARY_PATH", path.c_str(), 1) != 0)
      throw std::runtime_error("Cannot configure DSP library search path");
  }
  ~DspEnvironment() {
    if (had_previous_) (void)setenv("ADSP_LIBRARY_PATH", previous_.c_str(), 1);
    else (void)unsetenv("ADSP_LIBRARY_PATH");
  }
 private:
  bool had_previous_ = false;
  std::string previous_;
};

class StatisticsRuntime final : public opif::InferenceRuntime {
 public:
  StatisticsRuntime(opif::QnnRuntime& runtime, Callback& callback, const RunContext& context, int transport)
      : runtime_(runtime), callback_(callback), context_(context), transport_(transport),
        telemetry_([this] { telemetry_loop(); }) {}
  ~StatisticsRuntime() override {
    { std::lock_guard<std::mutex> lock(mail_mutex_); shutdown_ = true; notice_.reset(); }
    mail_cv_.notify_one();
    if (telemetry_.joinable()) telemetry_.join();
  }
  void set_listener(const opif::UdpServer* listener) noexcept { std::lock_guard<std::mutex> gate(callback_gate_); listener_.store(listener, std::memory_order_release); }
  void begin_session() override {
    if (!current()) throw std::runtime_error("Server is stopping or changing listener transport");
    runtime_.begin_session();
    std::lock_guard<std::mutex> gate(callback_gate_);
    ++generation_; performance_count_ = performance_next_ = 0;
    last_performance_update_ = last_update_ = Clock::time_point{};
    if (!current()) return;
    callback_.state("connected", std::string("Remote client connected on ") + transport_name(transport_) +
                    " 5555; full Cinque v3 graph runs on QNN HTP V81", transport_);
    callback_.stats(true, frames_, last_ms_, transport_);
  }
  opif::InferenceResponse infer(const opif::InferenceRequest& request) override {
    auto result = runtime_.infer(request);
    ++frames_; last_ms_ = result.inference_time_us / 1000.0;
    timespec completed{};
    if (clock_gettime(CLOCK_MONOTONIC, &completed) == 0) {
      performance_ms_[performance_next_] = last_ms_;
      performance_ns_[performance_next_] = static_cast<jlong>(completed.tv_sec) * 1000000000LL + completed.tv_nsec;
      performance_next_ = (performance_next_ + 1) % kPerformanceSamples;
      performance_count_ = std::min(performance_count_ + 1, kPerformanceSamples);
    }
    return result; // No JNI, image allocation or preview copying before protocol delivery.
  }
  void result_queued(opif::InferenceRequest&& request, uint32_t) noexcept override {
    std::unique_lock<std::mutex> lock(mail_mutex_, std::try_to_lock);
    if (!lock.owns_lock() || shutdown_) return; // display loss never blocks inference/network
    Notice note;
    note.request = std::move(request); note.generation = generation_.load(); note.preview_generation = preview_control.load();
    note.frames = frames_; note.ms = last_ms_; note.values = performance_ms_; note.times = performance_ns_;
    note.count = performance_count_; note.next = performance_next_;
    notice_ = std::move(note); // bounded one-waiting/one-running, moves existing network input buffer
    lock.unlock(); mail_cv_.notify_one();
  }
  void end_session() noexcept override {
    runtime_.end_session();
    ++generation_;
    std::lock_guard<std::mutex> gate(callback_gate_); // only lifecycle, never response/inference hot path
    { std::lock_guard<std::mutex> lock(mail_mutex_); notice_.reset(); }
    if (performance_count_ && current()) {
      const size_t start = (performance_next_ + kPerformanceSamples - performance_count_) % kPerformanceSamples;
      callback_.performance(performance_ms_, performance_ns_, start, performance_count_, transport_);
    }
    performance_count_ = performance_next_ = 0;
    callback_.stats(false, frames_, last_ms_);
    if (current()) callback_.state("listening", std::string("Waiting for a remote OPIF client on ") +
                                  transport_name(transport_) + " 5555", transport_);
    else if (!context_.stop.load()) callback_.state("switching", "Draining the previous listener; NPU model remains loaded");
  }
 private:
  struct Notice {
    opif::InferenceRequest request;
    uint64_t generation=0, preview_generation=0, frames=0; double ms=0;
    std::array<double,kPerformanceSamples> values{};
    std::array<jlong,kPerformanceSamples> times{};
    size_t count=0,next=0;
  };
  void telemetry_loop() {
    while (true) {
      Notice note;
      {
        std::unique_lock<std::mutex> lock(mail_mutex_);
        mail_cv_.wait(lock,[this]{return shutdown_ || notice_.has_value();});
        if (shutdown_) return;
        note=std::move(*notice_);notice_.reset();
      }
      std::lock_guard<std::mutex> gate(callback_gate_);
      if (note.generation != generation_.load() || !current()) continue;
      const auto now=Clock::now();
      if (now-last_performance_update_ >= std::chrono::milliseconds(500)) {
        const size_t start=(note.next+kPerformanceSamples-note.count)%kPerformanceSamples;
        callback_.performance(note.values,note.times,start,note.count,transport_);last_performance_update_=now;
      }
      if (now-last_update_ >= std::chrono::milliseconds(200)) {
        callback_.stats(true,note.frames,note.ms,transport_);last_update_=now;
      }
      if ((note.preview_generation & 1) && note.preview_generation == preview_control.load())
        callback_.preview(note.request,now,transport_);
    }
  }
  bool current() const noexcept {
    const auto* listener = listener_.load(std::memory_order_acquire);
    return listener && !listener->draining() && listener_current(context_, transport_);
  }
  opif::QnnRuntime& runtime_; Callback& callback_; const RunContext& context_; const int transport_;
  std::atomic<const opif::UdpServer*> listener_{nullptr};
  uint64_t frames_=0; double last_ms_=0;
  std::array<double,kPerformanceSamples> performance_ms_{};
  std::array<jlong,kPerformanceSamples> performance_ns_{};
  size_t performance_count_=0,performance_next_=0;
  Clock::time_point last_update_{},last_performance_update_{};
  std::atomic<uint64_t> generation_{0};
  std::mutex mail_mutex_,callback_gate_; std::condition_variable mail_cv_;
  std::optional<Notice> notice_; bool shutdown_=false; std::thread telemetry_;
};

void run_server(JNIEnv* env, jlong token, jstring model_path, jstring library_directory,
                jstring cache_directory, jstring cache_identity, jobject callback_object) {
  const auto context = find_context(token);
  if (!context) throw std::invalid_argument("Native run token does not exist");
  bool not_started = false;
  if (!context->started.compare_exchange_strong(not_started, true))
    throw std::logic_error("Native run token has already been used");
  Callback callback(env, callback_object, context);
  std::unique_lock<std::mutex> exclusive(active_run_mutex, std::try_to_lock);
  if (!exclusive.owns_lock()) {
    callback.state("error", "Another NPU server is still shutting down; wait before restarting");
    return;
  }
  if (context->stop.load()) { callback.state("stopped", "Start cancelled"); return; }
  try {
    const auto model = java_string(env, model_path, "Model path");
    const auto library = java_string(env, library_directory, "Native library directory");
    const auto cache = java_string(env, cache_directory, "Context cache directory");
    const auto identity = java_string(env, cache_identity, "Context cache identity", false);
    if (identity.size() != 64 || identity.find_first_not_of("0123456789abcdef") != std::string::npos)
      throw std::invalid_argument("Context cache identity must be a SHA-256 digest");
    char soc[PROP_VALUE_MAX]{};
    __system_property_get("ro.soc.model", soc);
    if (std::string(soc).find("SM8850") != 0)
      throw std::runtime_error(std::string("Requires Snapdragon 8 Elite Gen 5 (SM8850); this device reports ") + soc);
    callback.state("loading", "Loading the complete Cinque v3 NPU graph with a compiled context cache; CPU/GPU fallback is disabled");
    if (context->stop.load()) { callback.state("stopped", "Start cancelled"); return; }
    {
      DspEnvironment dsp(library);
      opif::QnnConfig config;
      config.model = model;
      config.plugin = library + "/libonnxruntime_providers_qnn.so";
      config.backend = library + "/libQnnHtp.so";
      config.cache_dir = cache;
      config.cache_identity = identity;
      // The SDK's constructor/graph compilation has no safe abort API here.
      // A stop remains latched during it and prevents opening any listener.
      opif::QnnRuntime runtime(config);
      while (!context->stop.load(std::memory_order_acquire)) {
        // Read after the costly QNN construction, and again after every drain:
        // changes made during loading or a previous switch use the final mode.
        const int transport = context->desired_transport.load(std::memory_order_acquire);
        {
          StatisticsRuntime statistics(runtime, callback, *context, transport);
          opif::UdpServer server(statistics, 5555, static_cast<opif::Transport>(transport));
          statistics.set_listener(&server);
          if (listener_current(*context, transport)) {
            callback.state("listening", std::string("NPU warmup passed; waiting for a remote OPIF client on ") +
                           transport_name(transport) + " 5555", transport);
            if (listener_current(*context, transport)) callback.stats(false, 0, 0);
          }
          try { server.run(context->stop, &context->desired_transport); }
          catch (...) { statistics.set_listener(nullptr); throw; }
          statistics.set_listener(nullptr);
        }
        // Old sockets have been closed before the next constructor binds.
        // A global stop or a Java callback failure always wins over a switch.
        if (!context->stop.load(std::memory_order_acquire)) {
          callback.state("switching", std::string("Changing listener to ") +
                         transport_name(context->desired_transport.load(std::memory_order_acquire)) +
                         " 5555; NPU model remains loaded");
        }
      }
      callback.state("stopping", "Draining accelerator work and releasing the NPU model");
    }
    callback.state("stopped", "NPU server stopped");
  } catch (const std::exception& error) {
    // Report startup failures before any readiness callback. QNN exceptions do
    // not select another execution provider or silently start a fake runtime.
    if (env->ExceptionCheck()) return;
    if (context->stop.load()) callback.state("stopped", "NPU server stopped");
    else callback.state("error", error.what());
  } catch (...) {
    if (context->stop.load()) callback.state("stopped", "NPU server stopped");
    else callback.state("error", "Unknown native NPU server failure");
  }
}
}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_com_example_openpilotinference_android_NativeBridge_createRun(JNIEnv* env, jclass) {
  try {
    std::lock_guard<std::mutex> lock(contexts_mutex);
    if (contexts.size() >= 8 || next_token == std::numeric_limits<jlong>::max())
      throw std::runtime_error("Too many unreleased native run tokens");
    const jlong token = next_token++;
    contexts.emplace(token, std::make_shared<RunContext>());
    return token;
  } catch (const std::exception& error) { throw_java(env, "java/lang/IllegalStateException", error.what()); }
  catch (...) { throw_java(env, "java/lang/IllegalStateException", "Cannot create native run token"); }
  return 0;
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_openpilotinference_android_NativeBridge_run(
    JNIEnv* env, jclass, jlong token, jstring model_path, jstring native_library_directory,
    jstring cache_directory, jstring cache_identity, jobject callback) {
  try { run_server(env, token, model_path, native_library_directory, cache_directory, cache_identity, callback); }
  catch (const std::exception& error) { throw_java(env, "java/lang/IllegalStateException", error.what()); }
  catch (...) { throw_java(env, "java/lang/IllegalStateException", "Cannot start native server"); }
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_openpilotinference_android_NativeBridge_setTransport(JNIEnv* env, jclass, jlong token, jint mode) {
  if (mode < 1 || mode > 3) {
    throw_java(env, "java/lang/IllegalArgumentException", "Transport must be UDP=1, TCP=2, or BOTH=3");
    return;
  }
  const auto context = find_context(token);
  if (!context) {
    throw_java(env, "java/lang/IllegalStateException", "Native run token does not exist");
    return;
  }
  // Setting a desired mode never clears a latched stop or creates another run.
  context->desired_transport.store(static_cast<int>(mode), std::memory_order_release);
  __android_log_print(ANDROID_LOG_INFO, kLogTag, "transport_requested=%s token=%lld",
                      transport_name(mode), static_cast<long long>(token));
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_openpilotinference_android_NativeBridge_requestStop(JNIEnv*, jclass, jlong token) {
  if (const auto context = find_context(token)) context->stop.store(true);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_openpilotinference_android_NativeBridge_releaseRun(JNIEnv*, jclass, jlong token) {
  std::lock_guard<std::mutex> lock(contexts_mutex);
  const auto found = contexts.find(token);
  if (found == contexts.end()) return;
  // The executing worker owns its shared_ptr and callback global reference;
  // removing the registry entry cannot destroy them while JNI run() is active.
  found->second->stop.store(true);
  contexts.erase(found);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_openpilotinference_android_NativeBridge_setPreviewEnabled(JNIEnv*, jclass, jboolean enabled) {
  set_preview_enabled(enabled == JNI_TRUE);
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_openpilotinference_android_NativeBridge_renderPreview(
    JNIEnv* env, jclass, jbyteArray packed, jintArray pixels) {
  if (!packed || !pixels || env->GetArrayLength(packed) != static_cast<jsize>(opif::preview::kPackedBytes) ||
      env->GetArrayLength(pixels) != static_cast<jsize>(opif::preview::kPixelCount)) {
    throw_java(env, "java/lang/IllegalArgumentException",
               "Preview requires packed byte[393216] and ARGB int[262144]");
    return;
  }
  jbyte* input = env->GetByteArrayElements(packed, nullptr);
  if (!input) return;
  jint* output = env->GetIntArrayElements(pixels, nullptr);
  if (output) {
    static_assert(sizeof(jint) == sizeof(uint32_t));
    opif::preview::render(reinterpret_cast<const uint8_t*>(input), opif::preview::kPackedBytes,
                          reinterpret_cast<uint32_t*>(output), opif::preview::kPixelCount);
    env->ReleaseIntArrayElements(pixels, output, 0);
  }
  env->ReleaseByteArrayElements(packed, input, JNI_ABORT);
}
