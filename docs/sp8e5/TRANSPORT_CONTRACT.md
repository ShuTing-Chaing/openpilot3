# OPIF transport failure contract (written before implementation)

The E2E harness uses the production C++ OPIF socket server, a clearly labelled deterministic accelerator fixture, the actual C3 TCP codec/client, its subprocess IPC and AsyncSession. It is not a phone/NPU or vehicle qualification. Every run writes commands, source hashes, server request events and JSON results.

Failures that must remain distinguishable:

1. An executed result arrives after its capture publication deadline: validate framing, identity and finite values, record terminal `expired`, consume its request, keep the session and subsequent fresh results.
2. An on-time response becomes stale while the consumer is busy: same terminal accounting; it cannot hide the next fresh response.
3. A missing or stalled result beyond the separate bounded transport watchdog, socket EOF, partial TCP send timeout or missing input is a hard fault. Never skip TCP bytes or claim a request executed without a validated terminal response.
4. Invalid output length/schema, nonfinite output (including a late output), changed epoch/session and unknown IDs are hard faults. Known terminal duplicates and packets from old sessions are ignored without advancing state twice.
5. Pending, completed and terminal-event queues remain bounded. A full input window is a history gap/fault rather than silent latest-input replacement. No input frame is silently skipped or repeated.
6. Full-result mode preserves 18,452 FP32 values. Compact mode is explicitly negotiated, preserves all retained float bytes and fails on unsupported encoding/layout/ABI. It never fabricates hidden state.
7. Close, process death and reconnect must not deliver old-context output into the next session. Context identity is verified at IPC and AsyncSession boundaries.

API: `AsyncSession.poll(timeout=0)` returns a fresh `(output, context, age, stats)` or None. `drain_events()` returns completed request events in sequence, including expired terminals, with seq/request_id, frame_id, eof_ns, context, opif_session_id, state_epoch, terminal and received_age_seconds. Stats retain the same identity. Route qualification uses both session ID and state epoch, and includes expired executed results in history accounting. A soft timeout never pretends to be an executed terminal.

OPIF compact negotiation: wire header version stays 1; START byte 2 output encoding=2, READY byte 3=2, output count=2068, ABI `sha256:<Cinque source>;op-supercombo-2068-f32-d33-s4-v2`; RESULT encoding=2/layout=2/count=2068. Payload is full floats `[0:2066]` then `[18450:18452]`. Existing full encoding=0/layout=0/count=18452/v1 is unchanged. Encoding=1 remains FLOAT16 and is never repurposed. Profile `result_schema` is either `full_f32` (default) or `control_heads_f32`; no silent fallback. The phone keeps full finite validation and all three recurrent states.

Epoch: a new random OPIF session starts at state_epoch=1; first request RESET_TEMPORAL initializes that epoch. A later accepted RESET increments epoch. Current C3 only resets the first request. A new session ID always denotes new history, even when epoch is again 1.

Initial required scenarios: delayed first result followed by fresh second; delayed consumer; ordinary full roundtrip; compact byte conservation; nonfinite delayed result rejected; disconnect; bounded stalled input/result; session identity retained in terminal events. Baseline must fail the first two soft-expiry scenarios before production edits. No new unit tests are added after implementation.

## Typed recovery faults

`external_host/faults.py` defines `TransportUnavailable` (network EOF/reset/connect failure, incomplete response watchdog, busy/draining accelerator), `HistoryResetRequired` (unsent input expired, bounded input queue exhausted, explicit request sequence gap) and `FatalModelFault` (identity/schema/finite/integrity failures). These extend HostError. The subprocess sends a closed `error_kind` enum; the parent reconstructs that class and AsyncSession preserves it. Unknown classifications are fatal. Recovery must start a new session/history and qualify it; an error string is never used to authorize recovery.

The separate terminal watchdog is 1 second by default, bounded to at most 2 seconds in Pipeline. Publication remains at the configured 50–200 ms capture deadline. Main-frame polling never waits on this watchdog. Input transmission retains its capture deadline; a partially sent TCP record cannot be deleted from the byte stream, so timeout requires reconnect/history reconstruction.

## Repeatable evidence

Run from this checkout:

```sh
python3 tools/sp8e5/transport_e2e.py --output docs/sp8e5/evidence/transport-repeat
```

The harness needs Python 3 and a C++17 compiler, compiles the current native codec and production Android OPIF server, and starts only loopback sockets and local child processes. It uses no camera, phone, Params, CAN, QCOM, GPU or NPU. Its inference fixture produces deterministic floats and labelled delays. Every output float retained in compact mode is compared as bytes against the exact full output.

`evidence/transport-baseline-verified/summary.json` captured both target failures before production edits: delayed executed request 477 and delayed consumer both raised the publication deadline exception, preventing new request 478 from being used. The earlier `transport-baseline` directory is invalid timing evidence: its Mac harness used CLOCK_MONOTONIC instead of Python's monotonic fallback; corrected before production edits and retained for audit.

`evidence/transport-final/summary.json` records 16 passing end-to-end scenarios: late output then fresh output, stale consumer then fresh output, full, compact conservation, late nonfinite, disconnect, watchdog, duplicate terminal, old-session terminal, unknown request, wrong schema, partial TCP record, conflicting duplicate, compact hidden nonfinite, bounded input window and expired unsent input. Server JSONL traces show executed request IDs; result JSON contains source hashes, real session IDs, terminal events, capture IDs, receipt/consumption ages and byte hashes. Negative cases verify the exact fault class, not merely that some exception occurred.

The native `.dylib` (Mac) and fixture executables are generated harness artifacts, not phone/C3 deployment binaries. Re-run this E2E after changes to the native server or transport. No IPC-copy or protocol performance improvement is claimed by these fixture timings. Actual phone/USB/Wi-Fi and isolated camera evidence remains a separate root integration step.
