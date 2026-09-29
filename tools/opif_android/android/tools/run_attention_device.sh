#!/system/bin/sh
set -eu
opif_base=/data/local/tmp/opif-attention-20260928
opif_apk=$(pm path com.example.openpilotinference.android | sed -n 's/^package://p' | head -n 1)
test -n "$opif_apk"
opif_libs=${opif_apk%/*}/lib/arm64
export LD_LIBRARY_PATH="$opif_libs"
export DSP_LIBRARY_PATH="$opif_libs"
export ADSP_LIBRARY_PATH="$opif_libs"
case "${1:-}" in
  pair) test ! -e "$opif_base/pair" ;;
  a1|a2|b1) test ! -e "$opif_base/$1.log" ;;
  *) echo 'Expected pair, a1, b1 or a2' >&2; exit 2 ;;
esac
dumpsys battery > "$opif_base/$1-battery-before.txt"
set +e
if [ "$1" = pair ]; then
  timeout 300 "$opif_base/attention_mask_device_e2e" "$opif_libs" \
    "$opif_base/baseline.onnx" "$opif_base/candidate.onnx" "$opif_base/pair" 410 0 \
    > "$opif_base/pair.log" 2>&1
  opif_result=$?
else
  opif_model="$opif_base/baseline.onnx"
  if [ "$1" = b1 ]; then opif_model="$opif_base/candidate.onnx"; fi
  timeout 240 "$opif_base/opif-server" --model "$opif_model" \
    --qnn-library "$opif_libs/libonnxruntime_providers_qnn.so" \
    --backend "$opif_libs/libQnnHtp.so" --benchmark 240 \
    --benchmark-input "$opif_base/benchmark-input.bin" \
    --benchmark-output "$opif_base/$1-outputs.bin" > "$opif_base/$1.log" 2>&1
  opif_result=$?
fi
set -e
dumpsys battery > "$opif_base/$1-battery-after.txt"
echo "$opif_result" > "$opif_base/$1-exit-code.txt"
exit "$opif_result"
