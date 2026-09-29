# Router implementation and repeatable evidence

This change owns `qnn_hotstandby.py`, `qnn_model.py`, `qnn_router.py`, `qnn_reconnect.py`, the router replay tools and this document. It does not enable remote control or modify qualification files, device Params, production processes, camera state or phone installation. Modeld publication and stable local cameraOdometry are integrated separately by the root task.

## Final behavior

The local runtime advances once per input tick and supplies a checked local output before routing. Missing or expired remote publications select that local output immediately. The adapter drains completion slots before preprocessing and after local execution without the old up-to-10-ms wait. Executed-but-expired results are consumed through the transport's terminal ledger, preserving recurrent execution history while rejecting their control output. Unknown execution/input gaps have a distinct typed recovery path.

Initial remote promotion requires 200 consecutive eligible publication ticks. A publication-only interruption requires ten consecutive eligible ticks before returning to remote preference. A new session/history generation clears old completion identity, desire edges and qualification progress and requires the full initial 200 again. These checks are in addition to the existing independent control qualification; shadow continues to publish only local output while reporting the hypothetical candidate selection.

Typed `TransportUnavailable` and `HistoryResetRequired` start a network-only background reconnect to the exact startup profile (host/port/model/schema pinned by a private deep copy). No QCOM work or preprocessing occurs in this worker. Each incident permits at most three attempts, with one- and two-second backoff. A ready session is transferred to the modeld frame thread, receives a new history generation and uses the phone protocol's new-session first-frame reset. Identity/schema/nonfinite faults remain isolated locally; exhaustion also latches locally. Closing the adapter prevents an in-flight reconnect from resurrecting it. There is no automatic host, cable, Wi-Fi address, model, or runtime migration.

The wrapper exposes `local_output`, `local_output_context`, `local_execution_time` for continuous local odometry. The selected `output_context` retains its actual capture frame/EOF and adds actual OPIF session, state epoch and request identifiers. `route_state.publish_seq` is independent and monotonic. Across source changes, selected capture IDs may move to an older capture from another source; neither metadata relabeling nor a publication pause conceals that fact. Per-session executed input ordering remains strict.

`revalidate_publication(output)` rechecks age and target windows after the caller's allocation/work and can select the already-hot local output without advancing publish_seq. Immediately before sending an already-built message, call with `retime_plan=False`; this validates the action's existing prediction target instead of silently retiming it. A changed output/context requires rebuilding or dropping the old message. This boundary performs no status-file I/O. Local expiry raises unavailability. The implementation also rechecks freshness after candidate action calculation, since action parsing itself consumes real time.

## Action contract and limits

`action_t` stays a prediction horizon in seconds. A learned `action` scalar (and a learned lateral `desired_curvature` scalar) is never scaled or retimed after inference. Each candidate logs its predicted target, required prediction target and the common intended actuation target after subtracting the model's existing smoothing compensation. An immutable scalar outside a 50-ms target window is rejected. For axes represented by a time-indexed plan, only the existing parser's horizon is updated to the current tick; this is not a new spatial ego-motion transformer.

The candidate actions are parsed into desired curvature and acceleration with the existing model parser before comparison. Promotion is deferred for stop disagreement, material brake/accelerate disagreement, opposite material lateral acceleration, or more than 1.5 m/s² acceleration/lateral-acceleration disagreement. There is no weighted fusion and no decay toward zero. Existing downstream smoothing remains in place. The 50-ms/1.5-m/s² candidate thresholds and the 200/10 frame hysteresis are provisional conservative shadow defaults, not a claimed driving qualification. A bounded learned-head target window is not exact arbitrary-time trajectory equivalence.

## Evidence

Failure cases were written in `ROUTER_FAILURES.md` before implementation. The original wrapper replay at `evidence/router-before` failed seven of eight scenarios, including suppressed local publication, permanent latching after a temporary gap, and accepting an action with a mismatched target. The final replay at `evidence/router-after` passes those eight scenarios/2,400 ticks plus a 250-tick publication-delay scenario. That added case advances the clock after run returns, verifies remote age 205ms switches to local age 55ms without a second publish_seq increment, then expires local and requires an exception. Its initial failure is retained at `evidence/publication-before`. The endpoint fixtures deliberately include a legacy endpoint with no reconnect capability; actual adapter input-gap recovery is covered by the next suite.

`evidence/adapter-before` records the pre-reconnect failure: the real adapter/session/parser/router chain stayed at one connection and latched on the injected disconnect. The later `evidence/adapter-final` uses the real profile loader, QnnModel, AsyncSession, Parser and QnnHotStandby over fixture QCOM/inference/link endpoints. It covers full and compact results, typed disconnect, input gap, nonfinite output isolation, expired terminal continuity, retry exhaustion and close-during-reconnect. Its five-frame initial qualification is explicitly a fixture speedup; production remains 200.

`evidence/adapter-tcp-final` adds the actual OPIF I/O subprocess, IPC, real TCP sockets and the production C++ phone protocol server. Only accelerator outputs, QCOM warp and the local model are fixtures. Full and compact output schemas each traverse 90 ticks; retained action bytes/parsed heads, omitted hidden state, actual session provenance and continuous local publication are checked. The trace and summaries include source hashes verified unchanged across each final run.

Reproduce from this checkout with its existing Python runtime:

```sh
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/router_replay.py --output /tmp/sp8e5-router
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/adapter_router_e2e.py --output /tmp/sp8e5-adapter
c++ -std=c++17 -O2 -pthread -I tools/opif_android/android/native tools/sp8e5/router_phone_fixture.cpp tools/opif_android/android/native/opif_protocol.cpp -o /tmp/sp8e5-router-phone
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/adapter_router_e2e.py --output /tmp/sp8e5-adapter-tcp --tcp-fixture /tmp/sp8e5-router-phone
```

These are repeatable software integration artifacts. Actual C3 QCOM preprocessing, real NPU state, real camera cadence, sustained device load, model accuracy and vehicle control are outside their fixture evidence and remain part of the root device integration/qualification work.
