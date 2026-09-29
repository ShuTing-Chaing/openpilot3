#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace opif::preview {
inline constexpr size_t kWidth = 1024;
inline constexpr size_t kHeight = 256;
inline constexpr size_t kPixelCount = kWidth * kHeight;
inline constexpr size_t kPlaneBytes = 128 * 256;
inline constexpr size_t kPackedBytes = 2 * 6 * kPlaneBytes;

inline uint32_t argb(uint8_t y, int u, int v) noexcept {
  const int luma = 298 * (static_cast<int>(y) - 16);
  const auto channel = [](int value) {
    return static_cast<uint32_t>(std::clamp((value + 128) / 256, 0, 255));
  };
  return 0xff000000u | (channel(luma + 409 * v) << 16) |
         (channel(luma - 100 * u - 208 * v) << 8) | channel(luma + 516 * u);
}

// Exact model input layout: camera, [Y00,Y10,Y01,Y11,U,V], 128, 256.
// Conversion is for display only; it does not alter the model's input buffer.
inline bool render(const uint8_t* packed, size_t packed_bytes,
                   uint32_t* pixels, size_t pixel_count) noexcept {
  if (!packed || !pixels || packed_bytes != kPackedBytes || pixel_count != kPixelCount)
    return false;
  for (size_t camera = 0; camera < 2; ++camera) {
    const auto* planes = packed + camera * 6 * kPlaneBytes;
    for (size_t row = 0; row < 128; ++row) {
      auto* top = pixels + row * 2 * kWidth + camera * 512;
      auto* bottom = top + kWidth;
      for (size_t col = 0; col < 256; ++col) {
        const size_t i = row * 256 + col;
        const int u = static_cast<int>(planes[4 * kPlaneBytes + i]) - 128;
        const int v = static_cast<int>(planes[5 * kPlaneBytes + i]) - 128;
        top[2 * col] = argb(planes[i], u, v);
        bottom[2 * col] = argb(planes[kPlaneBytes + i], u, v);
        top[2 * col + 1] = argb(planes[2 * kPlaneBytes + i], u, v);
        bottom[2 * col + 1] = argb(planes[3 * kPlaneBytes + i], u, v);
      }
    }
  }
  return true;
}
}  // namespace opif::preview
