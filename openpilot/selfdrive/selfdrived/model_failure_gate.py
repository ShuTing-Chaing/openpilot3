"""Report model failures using the selected runtime, never a saved preference."""


def big_model_failed(big_active, model_unavailable: bool, was_big_active: bool,
                     chestnut_present: bool, external_host_enabled: bool,
                     qnn_runtime_phase: str | None = None) -> bool:
  # Written only by modeld after the QNN wrapper chooses an output. This does
  # not select that output, waive its qualification, or enable an actuator.
  if qnn_runtime_phase == 'latched_local':
    return True
  if qnn_runtime_phase in ('shadow', 'qualifying', 'handover_wait', 'local_bridge', 'recovering', 'reconnecting'):
    return model_unavailable
  if qnn_runtime_phase == 'remote_active':
    # Router phase is atomic; ChestnutActive is a separately-written UI hint.
    # A read between the two writes must not turn healthy handover into a fault.
    return model_unavailable
  return big_active is False or model_unavailable or (was_big_active and not chestnut_present and not external_host_enabled)
