# OPIF 0.1.4 / dev-sp-8E5 build and replay

The source lives in `tools/opif_android`; the original Downloads project was not edited. The model remains the patch-kit output (`8cf7714f…fbd85961`). The native library is rebuilt; do not use `--reuse-jni`.

From this directory:

```sh
python3 android/e2e/protocol_roundtrip.py --out .cache/sp8e5-protocol
python3 android/e2e/preview_roundtrip.py --out .cache/sp8e5-preview
ANDROID_NDK_HOME=/private/tmp/opif-install-20260926/android-ndk-r29 python3 android/scripts/build_apk.py --model /Users/mile/Downloads/OpenPilotInference-Android/diagnostics/model-patch-kit-20260928/patched/model.onnx --deps /private/tmp/opif-install-20260926/deps --tools /private/tmp/opif-install-20260926/tools --output .cache/sp8e5-apk
```

Protocol changes: legacy START output=0, READY output=0/count18452/old ABI and RESULT encoding/layout0 remain full. New START byte2=2 negotiates `control_heads_f32`; READY byte3=2, count2068, ABI `sha256:404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4;op-supercombo-2068-f32-d33-s4-v2`; RESULT byte1=2, raw layout byte2=2. Compact bytes are full[0:2066] followed by full[18450:18452]. The entire real runtime output is still finite-checked before cropping. Graph recurrent states are unchanged. Queue microseconds now measure phone admission-to-worker-start, including the one waiting inference; they exclude upload/reassembly and inference itself.

Native preview no longer performs JNI/video copying in `infer`. The protocol queues the terminal result and attempts a socket flush first, then moves the existing request buffer into a bounded background mailbox. A preallocated JNI byte array and six Java packed-input slots bound video-copy memory; rendering owns at most two Bitmap objects. Preview remains at most10fps; stats and performance callbacks also run off the result path. A blocked UI may drop preview while model state progresses normally. Actual transport flushing can still be backpressured; this change does not claim that every byte has reached C3 before background work starts.

SP path is display-only on UDP5556; exact data contract is SP_PATH_PROTOCOL.md. Main path follows C3-published modelV2.position with MED/SBIG projection and SP throttle/experimental semantics. It is not a vehicle-realized track or an assertion of phone control. No path is shown for nonengaged/invalid calibration, missing same-frame pair, stale/old session or expired receipt TTL. The receipt TTL cannot measure unknown transit time; hard control freshness is enforced independently on C3. The view clears an overlay when expired without repainting old colored pixels into the video bitmap.

Host validation produces `result.json`, raw full/compact result bodies, `route.bin`, and `path.svg`. The protocol fixture has real sockets, frame assembly, replay and worker scheduling but synthetic inference. The preview fixture covers real UDP→production decoder/matcher/projector with synthetic geometry, not Android Canvas/device screenshots. Prior baseline exposed unsupported compact and zero queue telemetry. These are build/offline receipts only. Handset NPU conservation, actual App rendering, preview on/off latency, thermal/USB/Wi-Fi and actuator-isolated C3 router replay remain root-controlled device E2E gates.

Read-only installed-App observation through Android's existing ADB dumpsys:

```sh
adb shell am start -n com.example.openpilotinference.android/.MainActivity --ez preview_enabled true
adb shell dumpsys activity service com.example.openpilotinference.android/.InferenceService opif-preview-status
```

`OPIF_PREVIEW` JSON includes received/rejected packets, exact metadata of the last **Canvas-drawn** matching route, draw_count, phone-local timestamp/receipt TTL, six-slot history/two-bitmap bounds and errors. `last_draw_session_id` is unsigned decimal text. It is historical draw evidence; check its phone timestamp/TTL for current freshness. No new remote control endpoint was introduced.

Async phase regression (written before its fix):

```sh
python3 android/e2e/preview_async_roundtrip.py --out .cache/sp8e5-async-final
```

This uses production InputPreview/SpPath plus fixture-only Android/JNI substitutes through real UDP. 20Hz SP paths arrive before 10Hz phone image callbacks delayed75ms. Baseline global-latest selection matched0/20; matching bounded history produced20/20, exact identities, no displayed publication reversal. Raw event JSONL/status/result are preserved. C3 emits every20Hz SP path; phone video remains capped10fps. The preexisting strict source/session/epoch/EOF/request checks remain unchanged.
