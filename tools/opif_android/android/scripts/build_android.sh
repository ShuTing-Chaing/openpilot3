#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/../.." && pwd)"
deps_dir="${OPIF_ANDROID_DEPS:-$project_dir/.cache/android-deps}"
ndk_dir="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-$deps_dir/android-ndk-r29}}"
build_dir="${OPIF_ANDROID_BUILD:-$project_dir/.cache/android-build}"

if [[ ! -f "$ndk_dir/build/cmake/android.toolchain.cmake" ]]; then
  printf '%s\n' 'Android NDK is required. Set ANDROID_NDK_HOME to an installed NDK r29 or later.' >&2
  printf '%s\n' 'Official download: https://developer.android.com/ndk/downloads' >&2
  exit 1
fi
python3 "$project_dir/android/scripts/fetch_runtime.py" --output "$deps_dir"
cmake -S "$project_dir/android" -B "$build_dir" \
  -DCMAKE_TOOLCHAIN_FILE="$ndk_dir/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-31 \
  -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DORT_ROOT="$deps_dir"
cmake --build "$build_dir" --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
for platform_dir in "$ndk_dir"/toolchains/llvm/prebuilt/*; do
  stl_path="$platform_dir/sysroot/usr/lib/aarch64-linux-android/libc++_shared.so"
  if [[ -f "$stl_path" ]]; then
    cp "$stl_path" "$deps_dir/lib/libc++_shared.so"
    break
  fi
done
printf 'Built Android ARM64 server: %s/opif-server\n' "$build_dir"
