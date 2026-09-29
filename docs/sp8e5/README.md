# dev-sp-8E5: C3XL/OPIF continuous routing

Base: dev-sp-egpu b6ceca145001958f88c686d57feac8c9e8a7073c. Existing C3XL external-host runtime was selectively imported from the exact device sp-dev-mac snapshot; PORTED_DEVICE_FILES.json records its original hashes. Panda/opendbc/msgq/tinygrad gitlinks are unchanged. Android source is versioned under tools/opif_android, build/runtime/model artifacts stay out of Git.

Implemented: continuous local standby and source routing without waiting for remote completion; executed-but-expired result terminal accounting; typed transient reconnect to the same pinned endpoint/model/schema; initial200/recovery10 checked-selected-result qualification; action target-window and compatibility checks; transactionally prepared publication with a fresh final deadline check; local continuous cameraOdometry; off-thread status writes; SP-selected same-frame path telemetry and phone display; full/compact output negotiation and measured server queue time. No stale action amplitude decay or unqualified control enablement.

Phone release 0.1.4/code5 uses unchanged optimized model8cf7714f... and new JNI. Actual USB full/compact 200+200 frames passed and retained outputs matched byte-for-byte. Observed consumer age p50/p99: full73.83/88.42ms, compact64.29/81.01ms (one paired run, not a universal speed guarantee). First staged60s real-camera run passed1195 phone results/1218 model messages and real phone SP path Canvas drawing; the later qualification-count correction has independent software E2E and requires deployment-phase camera acceptance.

Wi-Fi has not passed stable repeated acceptance: one full200 run passed, subsequent compact startup and another power-save-disabled run hit the bounded history window. These failures are retained. Production preference remains the verified USB endpoint; no unsupported USB function or unmeasured QUIC/UDP replacement is enabled. Shared-memory IPC is a future measured candidate, not a claimed implementation.

Control qualification remains false. Hardware endpoint fixtures and shadow camera evidence do not constitute road/actuator qualification. Thresholds are development/shadow candidates; do not create a control qualification record from this README.

## Evidence and reproduction

- DESIGN.md: agreed architecture, including SP path rather than a fixed green overlay.
- FAILURES_AND_E2E.md and subsystem *_FAILURES.md: failures recorded before implementation.
- TRANSPORT_CONTRACT.md, ROUTER_IMPLEMENTATION.md, PUBLICATION_FAILURES.md: typed interfaces and repeatable E2E commands.
- tools/sp8e5/phone_e2e.py: real phone full/compact 20Hz replay; explicit --wifi-power-lease supports comparison under production radio policy.
- tools/sp8e5/run_camera_e2e.py: real cameras and production launcher/planner/controllers in an actuator-disconnected private namespace, restored in finally.
- tools/opif_android/docs/: phone source/protocol/build/read-only preview status contract. All source matching uses actual capture IDs/EOF/session/epoch; no new video stream is added.
- tools/sp8e5/deploy_branch.py: dry-run/install/rollback/retire with pinned identity, complete backups, exact commit/source readback and post-install camera evidence. Only the old current sp-dev-mac ref is retired; other branches and rollback refs remain.

Device run artifacts are under /data/qnn-host/dev-sp-8E5/evidence. Local delivery artifacts and installed APK receipts are under /Users/mile/Downloads/OpenPilotInference-Android/diagnostics/dev-sp-8E5-implementation. Source-freeze commit is separate from subsequent device acceptance receipts.
