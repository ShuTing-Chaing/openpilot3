"""Prepare one publication transaction without sending or advancing live state."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .wire import HostError


@dataclass(frozen=True)
class PreparedPublication:
  output: Any
  context: dict
  payload: Any
  state: tuple
  attempts: int


def clone_publication_state(state):
  """Clone only (PublishState, DesireHelper, RELC), sharing read-only Params.

  Cloning the whole tuple in one operation preserves the two child controllers'
  DH backreferences. Params contains native handles and is not copyable. These
  controllers only read it during update; no model, image or messaging object
  belongs in this transaction state.
  """
  if not isinstance(state, tuple) or len(state) != 3:
    raise ValueError('Publication state must be (PublishState, DesireHelper, RELC)')
  _publish, desire, edge = state
  external = (desire.alc.params, desire.lane_turn_controller.params, edge.params)
  return deepcopy(state, {id(value): value for value in external})


def _meta_key(value):
  return tuple(getattr(value, key, None) for key in ('frame_id', 'timestamp_eof', 'timestamp_sof'))


def _selection_key(model, output, context):
  # revalidation returns a new context dict even when nothing semantic changed.
  # Avoid numpy equality and pointer-based dict comparisons. The model output is
  # immutable here; every field consumed by modeld's publication is captured.
  fields = ('frame_id', 'frame_drop_ratio', 'vipc_dropped_frames', 'live_calib_seen',
            'lat_action_t', 'long_action_t', 'v_ego', 'lat_delay', 'long_delay',
            'lat_smooth_seconds', 'long_smooth_seconds', 'prev_acceleration', 'prev_curvature',
            'opif_session_id', 'opif_state_epoch', 'opif_request_id', 'preview_height', 'preview_calibrated')
  return (id(output), id(getattr(model, 'active', model)), getattr(model, 'source', None),
          _meta_key(context['meta_main']), _meta_key(context['meta_extra']),
          tuple(context.get(key) for key in fields))


def prepare_publication(model, output, context, build, state, *, clone_state=clone_publication_state):
  """Build at most twice, with final capture/action validation after each build.

  build(output, context, draft_state) must return unsent messages and may mutate
  only draft_state. Its action should be extracted using this selected model
  and context. On success the caller commits the returned state tuple and sends
  payload immediately, before any logging/Params/offline-recording work.

  The original state is never touched. Exceptions leave no transaction to send.
  The model's revalidator may switch source to the current local result, but it
  must never execute a model or increment the frame publication sequence.
  """
  revalidate = getattr(model, 'revalidate_publication', None)
  for attempt in range(1, 3):
    if revalidate is not None:
      output, context = revalidate(output, retime_plan=True)
    before = _selection_key(model, output, context)
    draft_state = clone_state(state)
    payload = build(output, context, draft_state)
    checked_output, checked_context = (revalidate(output, retime_plan=False) if revalidate is not None
                                       else (output, context))
    if _selection_key(model, checked_output, checked_context) == before:
      return PreparedPublication(checked_output, checked_context, payload, draft_state, attempt)
    # Discard both messages and draft state. The retry starts from the same
    # original live state, so FCW/turn/edge timers only advance once on commit.
    output, context = checked_output, checked_context
  raise HostError('Publication candidate changed again during the bounded rebuild')
