# SP path preview telemetry v1 (frozen before implementation)

C3 sends one little-endian UDP datagram to phone port **5556**. Exactly **672 bytes**, no IP fragmentation at normal >=1280 MTU. This channel is display-only, never accepted as inference/control input. No acknowledgements or resends; latest valid matching packet wins; globally newer unmatched packets do not suppress a valid same-frame pair. Restrict deployment to selected trusted USB/hotspot interface. It is not cryptographically authenticated; session/epoch matching prevents accidental stale association, not malicious impersonation.

| Offset | Type | Meaning |
|---:|---|---|
|0|4 bytes|ASCII `SPR1`|
|4|u8|version=1|
|5|u8|source: 1=local small model, 2=phone model|
|6|u16|flags: bit0 calibration valid, bit1 engaged, bit2 experimental mode, bit3 longitudinal control, bit4 allowThrottle; other bits forbidden|
|8|u64|SP publish_seq, strictly increasing per session+epoch|
|16|u64|actual OPIF session_id (not model identity; nonzero)|
|24|u64|state_epoch, initialized 1 at START; increments for accepted RESET_TEMPORAL with request_id>1; request1 reset initializes epoch1|
|32|u64|source request_id; 0 for local; actual selected remote request for phone|
|40|u64|source_capture_eof_ns, original C3 clock value also carried as OPIF client_timestamp_ns|
|48|u32|source narrow frame_id|
|52|u32|source wide frame_id|
|56|f32|capture age in milliseconds measured at C3 publish, finite 0..200|
|60|f32|SP path height offset in metres (extrinsicsCalibration.height); finite 0.2..4|
|64|f32|SP throttle blend 0..1; supplied actual SP style state, no inferred source color|
|68|u16|remaining display lifetime in ms, 1..200 (C3 sets from deadline-age)|
|70|u16|point count=33|
|72|18*f32|left then right row-major 3x3 calibrated 3D→512x256 model-image projection; MED then SBIG; all finite|
|144|99*f32|modelV2.position [x,y,z] interleaved, 33 points; finite|
|540|33*f32|modelV2.acceleration.x aligned with path points; finite|

The phone receives input image metadata `(session_id,state_epoch,request_id,capture_eof_ns)` directly from the executed OPIF request, never substitutes receive time for capture time. Join requires exact session+epoch+EOF. Source=phone also requires exact request ID. Source=local requires request_id=0. A pending route has bounded lifetime measured on the phone from its receipt (never subtract C3 and phone clocks); that lifetime is capped by C3's supplied remaining budget. Strict same-frame pairing is preferred to guessing motion compensation. Display age is an upper-bound estimate only if transport delay is separately known; label remaining receipt TTL accordingly.

Keep at most 6 completed-input images and 12 route packets (hard bounds); discard on session/generation change or expiry. No matching packet, invalid calibration, not engaged, unknown flags/version, future/invalid ranges or expired route means **no path**. Image may be shown with `waiting matching SP path`, `disengaged`, or `stale` status. Never label a predicted path as actuator-realized trajectory.

Rendering follows SP path: half-width 0.9m, height offset, 10..100m horizon clamp, projection/depth clipping; normal white↔green throttle semantics using supplied blend, experimental acceleration hue. Source is separate text, not color. Lane lines and phone raw prediction are not included in this v1 main-path channel.

C3 emits every20Hz publication (about13KB/s); only phone image conversion/delivery is capped10fps. Independently throttling both sides can select opposite capture parities. The phone searches bounded route history for the exact current image identity and highest matching publish_seq, and will not draw a publication older than one already drawn in that session+epoch. Network receive sequence highwater only rejects old/duplicate packets, never selects the path by itself.
