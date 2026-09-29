# Publication transaction failure contract (before helper implementation)

The output can cross its capture deadline or immutable action-target window during capnp message construction, even after routing succeeded. Message construction currently also advances PublishState confidence/FCW arrays, DesireHelper timers and its two child controllers, and RELC edge timers. Discarding a draft must not advance any of those live states.

Required failures: a remote becomes stale during construction while current local remains fresh; both expire; construction throws after mutating its state; a second local rebuild expires; semantic context changes require rebuilding but equal dict copies do not; finite request/session identity survives source change; prior action changes only on successful commit; no draft is sent before final validation. Revalidation itself must not advance recurrent model history or publish_seq.

Design contract: at most two construction attempts. Before each build call revalidate_publication(output, retime_plan=True), clone the original state, and build into unsent fresh messages using that clone. After construction call revalidate_publication(output, retime_plan=False). If output/source/capture/action-target context changed, discard draft and clone, then permit one local rebuild. Otherwise return the prepared payload and next state for a single commit and immediate send. A second change or any exception returns no prepared publication. The helper never sends, writes Params, changes prev_action or records an offline result.

State clone is restricted to (PublishState, DesireHelper, RELC). Preserve only the existing read-only Params handles at DH.alc.params, DH.lane_turn_controller.params and RELC.params; deepcopy the small Python controller graph and numpy history buffers together so child DH backreferences point to the cloned DH. Do not copy model runtimes, carstate, messaging objects, image buffers or process handles. Original state remains unchanged until root assigns the returned tuple.

E2E is written before helper code. It warms the real QnnHotStandby router across 250 camera ticks with deterministic endpoint/clock fixtures, builds a transactional multi-message fixture, and sends only the accepted payload through a real loopback datagram socket. Baseline builds without the second boundary and reproduces an over-deadline transmitted remote payload. Candidate runs cover fallback and rollback. Actual capnp/DH/RELC construction is separately checked read-only on the C3 and finally through root's isolated full camera pipeline; this fixture is not vehicle proof.

## Integration API and results

`prepare_publication(model, output, context, build, (publish_state, DH, RELC))` returns `PreparedPublication(output, context, payload, state, attempts)`. `build(selected_output, selected_context, draft_state)` creates fresh unsent message builders, extracts the action using the selected model/context, calls fill_model_msg using draft PublishState, and updates draft DH/RELC. It should return the action and four message builders together. Do not update prev_action, perform offline recording, publish Params or send any message inside build.

After successful return, rebind `(publish_state, DH, RELC) = prepared.state`, update output/context/action from prepared, assign prev_action, and immediately send the prepared messages. Deferred recording, Params metadata and preview work follow those sends. The tuple assignment commits only once and does not mutate model histories. The helper intentionally does not clone the models, camera frames or Cap'n Proto builders.

The unchanged case must compare context semantics, not dict object identity: revalidate_publication returns a fresh dict every call. The helper compares selected output/active model/source plus capture IDs/EOF and scalar publication/action-horizon fields. A changed candidate at the second construction boundary fails without sending instead of looping indefinitely.

Baseline receipt `evidence/publication-baseline/summary.json` shows an actual loopback-transmitted fixture payload with source qnn, capture 247 and age 205 ms. Candidate `evidence/publication-final/summary.json` has five passing cases: unchanged one-build publication; expired remote replaced by current local (capture 250, age 55 ms) after two builds; both expired; rebuilt local expired; build exception. Failed/dropped drafts leave all original controller counts and arrays unchanged. E2E does not claim real vehicle actuation.

The live C3 clone check (`publication-final/c3-state-clone.json`) constructed actual PublishState, DesireHelper and RELC under `/usr/local/venv/bin/python` with bytecode writes disabled, preserved the three native Params handles, verified both child DH links target the cloned parent, and verified the numpy history arrays are independent. No Params write, camera start or model run occurred. One observed clone duration is not a performance benchmark.

Repeat fixture E2E using an existing numpy-capable Python:

```sh
/Users/mile/Downloads/OpenPilotInference-Android/.venv/bin/python tools/sp8e5/publication_e2e.py --output docs/sp8e5/evidence/publication-repeat
```
