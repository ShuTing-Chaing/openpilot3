# Router integration replay failures (written before implementation)

The replay exercises the actual `QnnHotStandby` frame-loop wrapper with deterministic model endpoint fixtures. It is an adapter/router integration fixture, not NPU accuracy, physical transport, vehicle or road qualification. The production adapter and real camera/phone E2E remain required in the parent integration run.

Before changing the wrapper, retain the baseline result and source hashes. Cases:

1. A healthy large model qualifies, but a single completion-free tick suppresses publication despite a fresh local result. Require one valid local publication that tick and keep the remote session alive.
2. A late executed result precedes a fresh result. Require terminal accounting for both, discard the expired action and keep the newer candidate; no recursive-state reset solely because publication expired.
3. Recovery must accumulate consecutive eligible outputs, not switch back immediately on the first result. Repeated gaps restart recovery.
4. Capture/input gaps are not publication gaps. Hard-isolate the remote on input discontinuity or unaccounted execution order; keep fresh local output.
5. Nonfinite remote output is a hard error. Nonfinite or stale local output means no guaranteed hot standby and must raise system unavailability.
6. A nominally fresh learned scalar action can already miss its target-time window. Reject it; never change its scalar value to pretend it was resampled.
7. Opposed steering, stopping/braking disagreement or excessive normalized action disagreement must defer promotion. Never average incompatible paths.
8. Selected captures can be older across model-source changes. Preserve their true capture ID/EOF, advance independent publication sequence, keep local output/context available for continuous odometry.
9. Shadow mode may evaluate a hypothetical route but must always publish local output. No fixture changes production qualification or parameters.
10. Full and compact model result schemas must be explicit. Reject unknown schemas/lengths/nonfinite values; compact must omit hidden state rather than invent it.
11. A typed transport disconnect or unknown input-history interval must leave local publication running while a background worker reconnects to the exact same immutable profile. No QCOM work in that worker; no automatic host/USB/Wi-Fi/model change.
12. A new connection needs a distinct session identity and a clean history generation. Reset desire edges and require the full initial qualification sequence, not the short ten-frame publication-gap recovery.

## Qualification scheduling correction (before implementation)

Real camera-60d evidence supplied by the root: 1,195 phone results / 1,218 model ticks, maximum qualification progress 130, candidate always qualifying, with only remote_missing as an interruption. A tick can consume zero results and the next consume two sequential valid terminals. Counting consecutive camera ticks with a result prevents 200-result qualification under harmless asynchronous arrival jitter.

Qualification counts only a newly selected result whose parsed heads pass finite, capture age, action target and action compatibility checks. Superseded terminal heads are not implicitly qualified. A short no-completion tick publishes local and preserves qualification progress; it never reuses an old remote output. Missing eligible results for >=maximum_age, a genuinely expired completion, an actual incompatible candidate or a history reset clears progress. The first qualification still requires 200 checked results. Requalification after a real interruption still requires 10 checked results, and harmless empty ticks during recovery do not repeatedly erase progress. A previously qualified healthy session keeps its qualification through a short empty tick; current-output guards remain mandatory before selecting remote again.

The new qualification replay is written first and must show that periodic 0/2 completions cannot qualify the old code, then show qualified-result counting, no publication gap, no skipped input-history acceptance, no early qualification from superseded results, and true expiry/incompatibility/long-gap recovery. Existing router, adapter and publication E2Es are rerun after the correction.

Qualification implementation receipt: `evidence/qualification-baseline/summary.json` shows 600 old-code ticks with maximum good_frames=4 and no qualification under periodic 0/2 sequential completions. `evidence/qualification-final-v2/summary.json` passes six scenarios. First qualification occurs at tick 271 after exactly 200 actually selected and checked results, even though 250 terminal responses were accounted; superseded heads did not inflate qualification. The shadow scenario reaches candidate qualification but never selects phone control. Expired/incompatible/long-gap cases each require ten newly checked results after the reset, including short empty ticks between those results. Input-history discontinuity remains a hard isolation in the endpoint fixture.

The router exports `qualification_unit=checked_selected_results` and `qualification_reset` (expired_completion / eligible_gap / candidate_failed) with its status. Short no-completion ticks preserve the existing counter and eligibility history but always use local for that tick; they never reuse an old remote action. The budget for an eligible-result gap is still maximum_age (normally 200 ms). A new session resets last_eligible_at along with all qualification/history state.

Repeat from the checkout:

```sh
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/qualification_replay.py --output docs/sp8e5/evidence/qualification-repeat
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/router_replay.py --output docs/sp8e5/evidence/router-repeat
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/adapter_router_e2e.py --output docs/sp8e5/evidence/adapter-repeat
PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/publication_e2e.py --output docs/sp8e5/evidence/publication-repeat
```
13. Permanent model/ABI/nonfinite faults never trigger reconnect. Bounded transient retry exhaustion becomes a visible hard fault. Closing during reconnect must close a newly-created session and cannot resurrect a stopped adapter.
14. A candidate can expire after router.run returns while modeld allocates/fills messages or persists descriptive status. Immediately before action extraction/publication, revalidate source age and learned-action target windows. Re-select the already-hot local result without incrementing publish_seq again; if local is also invalid, raise unavailable. A previously-built message must not be sent if revalidation selected a different output/context.

`tools/sp8e5/adapter_router_e2e.py` exercises the real profile loader, QnnModel, AsyncSession, Parser and QnnHotStandby together. Only Params/QCOM tensors/phone inference link and local inference are fixtures; it never starts a camera or accesses vehicle controls. It records full-vs-compact byte/head equivalence, terminal provenance, reconnect generation, publication continuity, and identity-fault isolation. Its shortened fixture qualification is explicitly not a production qualification result.

Run `PYTHONPATH=. /Users/mile/Desktop/mo-op/.venv/bin/python tools/sp8e5/router_replay.py --output <directory>` from this checkout. The JSONL records capture IDs/EOF, selected source, route state and failure reason for every tick; summary JSON and source SHA256 make the fixture repeatable. Timing/action thresholds are provisional shadow defaults and require measured device/control qualification before enabling remote control.
