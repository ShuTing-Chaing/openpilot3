#include "../native/preview.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

int main() {
  using namespace opif::preview;
  std::vector<uint8_t> packed(kPackedBytes, 128);
  std::vector<uint32_t> pixels(kPixelCount + 2, 0x12345678);
  auto* output = pixels.data() + 1;
  const auto fill_camera = [&](size_t camera, uint8_t y, uint8_t u, uint8_t v) {
    auto start = packed.begin() + camera * 6 * kPlaneBytes;
    std::fill(start, start + 4 * kPlaneBytes, y);
    std::fill(start + 4 * kPlaneBytes, start + 5 * kPlaneBytes, u);
    std::fill(start + 5 * kPlaneBytes, start + 6 * kPlaneBytes, v);
  };
  const auto check_sides = [&](uint32_t left, uint32_t right) {
    const auto original = packed;
    assert(render(packed.data(), packed.size(), output, kPixelCount));
    assert(packed == original);
    for (size_t y = 0; y < kHeight; ++y)
      for (size_t x = 0; x < kWidth; ++x)
        assert(output[y * kWidth + x] == (x < 512 ? left : right));
    assert(pixels.front() == 0x12345678 && pixels.back() == 0x12345678);
  };
  fill_camera(0, 16, 128, 128);
  fill_camera(1, 235, 128, 128);
  check_sides(0xff000000, 0xffffffff);
  // Canonical limited-range red and blue samples, rounded using BT.601.
  fill_camera(0, 81, 90, 240);
  fill_camera(1, 41, 240, 110);
  check_sides(0xffff0000, 0xff0000ff);
  fill_camera(0, 145, 54, 34);
  fill_camera(1, 0, 128, 128);
  check_sides(0xff00ff01, 0xff000000);

  // Different luminance in each 2x2 packed plane catches Y10/Y01 swaps.
  fill_camera(0, 16, 128, 128);
  fill_camera(1, 235, 128, 128);
  const std::array<uint8_t, 4> luma{16, 82, 145, 235};
  const std::array<uint32_t, 4> gray{0xff000000, 0xff4d4d4d, 0xff969696, 0xffffffff};
  for (size_t plane = 0; plane < 4; ++plane)
    std::fill_n(packed.data() + plane * kPlaneBytes, kPlaneBytes, luma[plane]);
  assert(render(packed.data(), packed.size(), output, kPixelCount));
  for (size_t y = 0; y < kHeight; ++y)
    for (size_t x = 0; x < 512; ++x)
      assert(output[y * kWidth + x] == gray[(x % 2) * 2 + (y % 2)]);

  // Exhaust the neutral luma range; all four pixels share the same chroma.
  fill_camera(0, 0, 128, 128);
  for (size_t plane = 0; plane < 4; ++plane)
    for (size_t i = 0; i < kPlaneBytes; ++i) packed[plane * kPlaneBytes + i] = i % 256;
  assert(render(packed.data(), packed.size(), output, kPixelCount));
  for (size_t x = 0; x < 512; ++x) {
    const int level = std::clamp(static_cast<int>((298 * (static_cast<int>(x / 2) - 16) + 128) / 256), 0, 255);
    assert(output[x] == (0xff000000u | static_cast<uint32_t>(level * 0x010101)));
  }

  const auto unchanged = pixels;
  assert(!render(nullptr, kPackedBytes, output, kPixelCount));
  assert(!render(packed.data(), kPackedBytes, nullptr, kPixelCount));
  assert(!render(packed.data(), kPackedBytes - 1, output, kPixelCount));
  assert(!render(packed.data(), kPackedBytes + 1, output, kPixelCount));
  assert(!render(packed.data(), kPackedBytes, output, kPixelCount - 1));
  assert(!render(packed.data(), kPackedBytes, output, kPixelCount + 1));
  assert(pixels == unchanged);
  std::cout << "Preview color, packing, camera order, bounds and input immutability checks passed\n";
}
