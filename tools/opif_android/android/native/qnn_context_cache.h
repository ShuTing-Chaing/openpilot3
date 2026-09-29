#pragma once

// App-private EPContext storage. No ONNX interpretation or inference happens here.
// A directory becomes readable only after the caller has validated the original
// model's provenance/ABI and completed a real HTP warmup.
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

namespace opif::context_cache {

// Small streaming SHA-256 implementation avoids an Android libcrypto dependency.
class Sha256 {
 public:
  void update(const void* input, size_t size) {
    const auto* bytes = static_cast<const uint8_t*>(input);
    bytes_ += size;
    while (size) {
      const size_t part = std::min(size, block_.size() - used_);
      std::memcpy(block_.data() + used_, bytes, part);
      used_ += part; bytes += part; size -= part;
      if (used_ == block_.size()) { transform(); used_ = 0; }
    }
  }
  std::string finish() {
    const uint64_t bits = bytes_ * 8;
    const uint8_t one = 0x80, zero = 0;
    update(&one, 1);
    while (used_ != 56) update(&zero, 1);
    std::array<uint8_t, 8> length{};
    for (size_t i = 0; i < 8; ++i) length[7 - i] = static_cast<uint8_t>(bits >> (8 * i));
    update(length.data(), length.size());
    constexpr char hex[] = "0123456789abcdef";
    std::string result(64, '0');
    for (size_t i = 0; i < 32; ++i) {
      const auto byte = static_cast<uint8_t>(state_[i / 4] >> (24 - 8 * (i % 4)));
      result[2 * i] = hex[byte >> 4]; result[2 * i + 1] = hex[byte & 15];
    }
    return result;
  }
 private:
  static uint32_t rotate(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
  void transform() {
    constexpr std::array<uint32_t, 64> k{
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    std::array<uint32_t, 64> w{};
    for (size_t i = 0; i < 16; ++i)
      w[i] = (uint32_t(block_[i*4]) << 24) | (uint32_t(block_[i*4+1]) << 16) |
             (uint32_t(block_[i*4+2]) << 8) | uint32_t(block_[i*4+3]);
    for (size_t i = 16; i < 64; ++i) {
      const uint32_t s0 = rotate(w[i-15],7) ^ rotate(w[i-15],18) ^ (w[i-15] >> 3);
      const uint32_t s1 = rotate(w[i-2],17) ^ rotate(w[i-2],19) ^ (w[i-2] >> 10);
      w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    auto s = state_;
    for (size_t i = 0; i < 64; ++i) {
      const uint32_t sum1 = rotate(s[4],6) ^ rotate(s[4],11) ^ rotate(s[4],25);
      const uint32_t ch = (s[4] & s[5]) ^ (~s[4] & s[6]);
      const uint32_t t1 = s[7] + sum1 + ch + k[i] + w[i];
      const uint32_t sum0 = rotate(s[0],2) ^ rotate(s[0],13) ^ rotate(s[0],22);
      const uint32_t maj = (s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]);
      s = {t1 + sum0 + maj, s[0], s[1], s[2], s[3] + t1, s[4], s[5], s[6]};
    }
    for (size_t i = 0; i < 8; ++i) state_[i] += s[i];
  }
  std::array<uint32_t, 8> state_{
      0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  std::array<uint8_t, 64> block_{};
  uint64_t bytes_ = 0;
  size_t used_ = 0;
};

inline std::string sha256(const std::string& value) {
  Sha256 hash; hash.update(value.data(), value.size()); return hash.finish();
}

class Fd {
 public:
  explicit Fd(int fd) : fd_(fd) {
    if (fd < 0) throw std::runtime_error(std::string("QNN cache I/O: ") + std::strerror(errno));
  }
  ~Fd() { close(fd_); }
  Fd(const Fd&) = delete;
  Fd& operator=(const Fd&) = delete;
  int get() const { return fd_; }
 private:
  int fd_;
};

inline void check_private(const std::string& path, bool directory) {
  struct stat st{};
  if (lstat(path.c_str(), &st) != 0 || st.st_uid != geteuid() || (st.st_mode & 0077) ||
      (directory ? !S_ISDIR(st.st_mode) : !S_ISREG(st.st_mode)))
    throw std::runtime_error("QNN cache must be a private, owned regular file/directory");
}

inline std::pair<std::string, uint64_t> digest_file(const std::string& path, bool sync = false) {
  Fd file(open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
  struct stat st{};
  if (fstat(file.get(), &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 ||
      uint64_t(st.st_size) > uint64_t(std::numeric_limits<int32_t>::max()))
    throw std::runtime_error("QNN context is missing, empty, nonregular or exceeds ONNX size limit");
  if (sync && fchmod(file.get(), 0600)) throw std::runtime_error("Cannot protect QNN context");
  Sha256 hash;
  std::array<uint8_t, 64 * 1024> buffer{};
  uint64_t total = 0;
  for (;;) {
    const auto count = read(file.get(), buffer.data(), buffer.size());
    if (count < 0 && errno == EINTR) continue;
    if (count < 0) throw std::runtime_error("QNN context read failed");
    if (!count) break;
    hash.update(buffer.data(), static_cast<size_t>(count)); total += count;
  }
  if (total != uint64_t(st.st_size) || (sync && fsync(file.get())))
    throw std::runtime_error("QNN context changed or could not be synced");
  return {hash.finish(), total};
}

class Store {
 public:
  Store(std::string root, const std::string& identity)
      : root_(std::move(root)), key_(sha256(identity)), ready_(root_ + "/" + key_),
        lock_(open_lock(root_)) {
    if (identity.empty()) throw std::runtime_error("QNN cache identity is required");
    // Only one initializer may replace/prune caches; a concurrent initializer can
    // still compile normally rather than waiting behind a long graph compilation.
    if (flock(lock_.get(), LOCK_EX | LOCK_NB)) throw std::runtime_error("QNN cache initializer busy");
    for (const auto& entry : std::filesystem::directory_iterator(root_)) {
      if (entry.path().filename().string().rfind(".pending-", 0) == 0)
        std::filesystem::remove_all(entry.path());
    }
  }
  ~Store() {
    std::error_code ec;
    if (!pending_.empty()) std::filesystem::remove_all(pending_, ec);
  }
  Store(const Store&) = delete;
  Store& operator=(const Store&) = delete;

  const std::string& key() const { return key_; }
  std::string load() const {
    if (!std::filesystem::exists(ready_)) return {};
    check_private(ready_, true);
    const std::string model = ready_ + "/context.onnx";
    const std::string manifest = ready_ + "/manifest";
    check_private(model, false); check_private(manifest, false);
    Fd file(open(manifest.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    std::array<char, 256> data{};
    const auto size = read(file.get(), data.data(), data.size());
    if (size <= 0 || size == static_cast<ssize_t>(data.size()))
      throw std::runtime_error("Invalid QNN cache manifest size");
    const auto digest = digest_file(model);
    if (std::string(data.data(), static_cast<size_t>(size)) != manifest_text(digest))
      throw std::runtime_error("QNN cache identity/integrity mismatch");
    return model;
  }

  std::string begin() {
    if (!pending_.empty()) throw std::runtime_error("QNN cache generation already active");
    std::string pattern = root_ + "/.pending-" + key_ + "-XXXXXX";
    std::vector<char> path(pattern.begin(), pattern.end()); path.push_back('\0');
    if (!mkdtemp(path.data())) throw std::runtime_error("Cannot create QNN cache staging directory");
    pending_ = path.data();
    return pending_ + "/context.onnx";
  }

  // Call only after original model provenance/ABI verification AND HTP warmup.
  void commit() {
    if (pending_.empty()) throw std::runtime_error("No pending QNN context");
    const std::string model = pending_ + "/context.onnx";
    const auto digest = digest_file(model, true);
    const auto text = manifest_text(digest);
    {
      Fd file(open((pending_ + "/manifest").c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600));
      size_t written = 0;
      while (written < text.size()) {
        const auto count = write(file.get(), text.data() + written, text.size() - written);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) throw std::runtime_error("Cannot write QNN cache manifest");
        written += static_cast<size_t>(count);
      }
      if (fsync(file.get())) throw std::runtime_error("Cannot sync QNN cache manifest");
    }
    sync_directory(pending_);
    invalidate();
    if (rename(pending_.c_str(), ready_.c_str())) throw std::runtime_error("Cannot commit QNN context");
    pending_.clear();
    sync_directory(root_);
    // This directory is dedicated to EPContext. Retain only the current key to
    // avoid accumulating a model-size blob after every driver or model update.
    for (const auto& entry : std::filesystem::directory_iterator(root_)) {
      const auto name = entry.path().filename().string();
      if (name != key_ && name.size() == 64 &&
          std::all_of(name.begin(), name.end(), [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); }))
        std::filesystem::remove_all(entry.path());
    }
  }
  void invalidate() {
    std::error_code ec;
    std::filesystem::remove_all(ready_, ec);
    if (ec) throw std::runtime_error("Cannot invalidate QNN context");
  }
 private:
  static int open_lock(const std::string& root) {
    if (mkdir(root.c_str(), 0700) && errno != EEXIST)
      throw std::runtime_error("Cannot create QNN cache directory");
    check_private(root, true);
    return open((root + "/.lock").c_str(), O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
  }
  static void sync_directory(const std::string& path) {
    Fd dir(open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    if (fsync(dir.get())) throw std::runtime_error("Cannot sync QNN cache directory");
  }
  std::string manifest_text(const std::pair<std::string, uint64_t>& digest) const {
    return "OPIF_QNN_EMBEDDED_CONTEXT_V1\n" + key_ + "\n" + digest.first + "\n" + std::to_string(digest.second) + "\n";
  }
  std::string root_, key_, ready_, pending_;
  Fd lock_;
};
}  // namespace opif::context_cache
