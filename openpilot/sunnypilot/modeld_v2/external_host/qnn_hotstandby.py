"""Per-drive QNN arbitration with a small model executed on every camera frame."""
import json
import os
from pathlib import Path
import time

import numpy as np

from .wire import HostError
from .faults import HistoryResetRequired
from .qnn_router import action_context, candidate_action, compatible_actions

STATUS_PATH = Path('/dev/shm/qnn-host-status.json')


class StaleLocalOutput(HostError):
  """Drop this publication; the next camera frame may still be valid."""


def boottime():
  return time.clock_gettime(time.CLOCK_BOOTTIME)


def write_status(row):
  """Status is descriptive; it is never consumed as an authorization gate."""
  temporary = STATUS_PATH.with_suffix(f'.{os.getpid()}.tmp')
  try:
    temporary.write_text(json.dumps(row, sort_keys=True) + '\n')
    temporary.replace(STATUS_PATH)
  except OSError:
    # Dashboard storage failure cannot delay or replace valid local inference.
    try:
      temporary.unlink(missing_ok=True)
    except OSError:
      pass


class QnnHotStandby:
  """Fixed frame-tick routing with local history always advancing.

  Missing/expired publications are recoverable; unknown execution history and
  invalid model data isolate the remote for this drive. Qualification remains a
  separate explicit gate. No network wait or handover publication freeze.
  """
  external_host = True
  qnn_hotstandby = True

  def __init__(self, remote, local, profile, *, on_failed, clock=boottime, status_sink=write_status):
    if local is None or local.chestnut:
      raise HostError('QNN requires a local small model for every-frame hot standby')
    for model in (local, remote):
      if model.constants.MODEL_FREQ != 20 or model.constants.DESIRE_LEN != 8:
        raise HostError('QNN hot standby requires compatible 20 Hz and 8-class desire runtimes')
      if len(model.vision_input_names) != 2 or sum('big' in key for key in model.vision_input_names) != 1:
        raise HostError('QNN hot standby requires one road and one wide view')
    self.remote, self.local, self.active = remote, local, local
    self.clock, self.status_sink, self.on_failed = clock, status_sink, on_failed
    self.allow_control = profile.get('allow_control') is True
    self.maximum_age = float(profile.get('maximum_result_age_seconds', .2))
    if not .05 <= self.maximum_age <= .2:
      raise HostError('QNN capture-to-publication age must be 50 to 200 ms')
    self.qualifying_frames = 200
    self.recovery_frames = 10
    self.action_target_tolerance = .05
    self.maximum_accel_difference = 1.5
    self.maximum_lateral_difference = 1.5
    self.ever_qualified = False
    self.recovering = False
    self.history_identity = None
    self.history_generation = getattr(remote, 'history_generation', 0)
    self.last_remote_seq = None
    self.publish_seq = 0
    self.route_state = {}
    self.local_output = self.local_output_context = None
    self.local_execution_time = 0.
    self.good_frames = self.local_runs = self.remote_outputs = 0
    self.last_eligible_at = None
    self.last_frame = self.last_eof = self.last_remote_frame = None
    self.last_published_frame = None
    self.last_published_context = None
    self.last_input_age_ms = None
    self.last_input_frame = None
    self.last_input_eof_ns = None
    self.startup_good_frames = 0
    self.remote_started = False
    self.submit_context = self.output_context = None
    self.output_execution_time = 0.
    self.phase = 'qualifying' if self.allow_control else 'shadow'
    self.source = 'local'
    self.failure_reason = ''
    self.handover_reason = ''
    self.last_status_at = -float('inf')
    self.last_status_phase = None
    self.numpy_inputs = dict(local.numpy_inputs, **remote.numpy_inputs)
    self._write_status()

  def __getattr__(self, name):
    return getattr(self.active, name)

  @property
  def chestnut(self):
    return self.source == 'qnn'

  @property
  def vision_input_names(self):
    return self.remote.vision_input_names

  @property
  def desire_key(self):
    return self.remote.desire_key

  @property
  def lat_delay(self):
    return self.active.lat_delay

  @lat_delay.setter
  def lat_delay(self, value):
    self.local.lat_delay = self.remote.lat_delay = value

  @property
  def PLANPLUS_CONTROL(self):
    return self.active.PLANPLUS_CONTROL

  @PLANPLUS_CONTROL.setter
  def PLANPLUS_CONTROL(self, value):
    self.local.PLANPLUS_CONTROL = self.remote.PLANPLUS_CONTROL = value

  @property
  def expected_frame_delay(self):
    return getattr(self.active, 'expected_frame_delay', .05)

  def _write_status(self):
    now = self.clock()
    if self.phase == self.last_status_phase and now - self.last_status_at < 1:
      return
    self.last_status_phase, self.last_status_at = self.phase, now
    self.status_sink({'schema': 'qnn-host-status-v1', 'source': self.source, 'phase': self.phase,
                      'allow_control': self.allow_control, 'good_frames': self.good_frames,
                      'qualification_frames': self.qualifying_frames, 'local_runs': self.local_runs,
                      'remote_outputs': self.remote_outputs, 'failure_reason': self.failure_reason,
                      'startup_good_frames': self.startup_good_frames, 'remote_started': self.remote_started,
                      'input_age_ms': self.last_input_age_ms, 'input_frame': self.last_input_frame,
                      'input_eof_ns': self.last_input_eof_ns, 'maximum_age_ms': self.maximum_age * 1000,
                      'handover_reason': self.handover_reason, 'last_published_frame': self.last_published_frame,
                      'route': self.route_state,
                      'execution_mode': self.remote.profile.get('execution_mode', 'npu_only'),
                      'transport': 'qnn_wifi', 'updated_boottime': now})

  def _latch(self, reason):
    if self.phase == 'latched_local':
      return
    self.phase, self.source, self.active = 'latched_local', 'local', self.local
    self.failure_reason = str(reason)
    self.good_frames = 0
    self.last_eligible_at = None
    try:
      self.remote.close()
    except Exception as error:
      self.failure_reason += f'; remote cleanup failed: {error}'
    finally:
      self.on_failed(self.failure_reason)
      self._write_status()

  def _context_for(self, model):
    context = dict(self.submit_context)
    # The incoming context uses the previously published source's smoothing.
    # Each runtime needs its own action horizon before inference, including
    # during the initial local-only qualification period.
    context['lat_delay'] += model.LAT_SMOOTH_SECONDS - self.active.LAT_SMOOTH_SECONDS
    context['long_delay'] += model.LONG_SMOOTH_SECONDS - self.active.LONG_SMOOTH_SECONDS
    delay = getattr(model, 'expected_frame_delay', .05)
    context['lat_action_t'] = context['lat_delay'] + delay + .025
    context['long_action_t'] = context['long_delay'] + delay + .025
    context['lat_smooth_seconds'] = model.LAT_SMOOTH_SECONDS
    context['long_smooth_seconds'] = model.LONG_SMOOTH_SECONDS
    return context

  def _arguments_for(self, model, bufs, transforms, inputs, context):
    by_view = {'big' in key: key for key in bufs}
    model_bufs = {key: bufs[by_view['big' in key]] for key in model.vision_input_names}
    model_tfms = {key: transforms[by_view['big' in key]] for key in model.vision_input_names}
    # ModelState.run mutates desire in place. Neither runtime may observe the
    # other's edge detector or history state.
    model_inputs = {key: np.array(value, dtype=np.float32, copy=True) for key, value in inputs.items()}
    model_inputs[model.desire_key] = np.array(inputs[self.desire_key], dtype=np.float32, copy=True)
    model_inputs['action_t'] = np.array([context['lat_action_t'], context['long_action_t']], np.float32)
    if 'lateral_control_params' in model.numpy_inputs:
      model_inputs['lateral_control_params'] = np.array([context['v_ego'], context['lat_delay']], np.float32)
    return model_bufs, model_tfms, model_inputs

  def _fresh(self, context):
    return context is not None and 0 <= self.clock() - context['meta_main'].timestamp_eof / 1e9 < self.maximum_age

  @staticmethod
  def _valid(output):
    return isinstance(output, dict) and bool(output) and all(
      np.isfinite(value).all() for value in output.values() if isinstance(value, np.ndarray))

  def _account_completions(self, events, current_frame):
    for event in events:
      identity = (event.get('opif_session_id'), event.get('state_epoch'))
      if self.history_identity is None:
        self.history_identity = identity
      elif identity != self.history_identity:
        if event.get('soft_reset') is not True:
          raise HostError('Remote execution history epoch changed without requalification')
        self.history_identity = identity
      if event.get('soft_reset') is True:
        # The client-side admission window requested RESET_TEMPORAL on the
        # existing TCP session. Accept that sanctioned reset while preserving
        # the transport and restarting only continuity/qualification.
        self.last_remote_seq = self.last_remote_frame = None
        self.good_frames = 0
        self.last_eligible_at = None
      seq, frame = event['seq'], event['frame_id']
      if event['terminal'] not in ('executed', 'expired'):
        raise HostError('Remote input execution was not confirmed')
      if self.last_remote_seq is not None and seq != self.last_remote_seq + 1:
        raise HostError('Remote execution terminal sequence has a gap')
      if frame > current_frame or (self.last_remote_frame is not None and frame != self.last_remote_frame + 1):
        raise HostError('Remote executed input sequence is duplicated, skipped or in the future')
      self.last_remote_seq, self.last_remote_frame = seq, frame
      self.remote_outputs += 1

  def run(self, bufs, transforms, inputs, after_enqueue=None):
    context = self.submit_context
    if context is None:
      raise HostError('QNN hot standby requires capture-time publication context')
    meta = context['meta_main']
    self.last_input_frame = int(meta.frame_id)
    self.last_input_eof_ns = int(meta.timestamp_eof)
    self.last_input_age_ms = (self.clock() - meta.timestamp_eof / 1e9) * 1000
    local_context, remote_context = self._context_for(self.local), self._context_for(self.remote)
    contiguous = self.last_frame is None or (meta.frame_id == self.last_frame + 1 and meta.timestamp_eof > self.last_eof)
    if not contiguous and self.remote_started:
      reason = 'Camera discontinuity invalidated remote model history'
      if hasattr(self.remote, 'request_recovery') and self.phase != 'latched_local':
        self.remote.request_recovery(HistoryResetRequired(reason))
      else:
        self._latch(reason)
    if not self.remote_started:
      self.startup_good_frames = self.startup_good_frames + 1 if contiguous else 1
    self.last_frame, self.last_eof = meta.frame_id, meta.timestamp_eof
    if not self._fresh(local_context):
      age_ms = (self.clock() - local_context['meta_main'].timestamp_eof / 1e9) * 1000
      if self.remote_started and hasattr(self.remote, 'request_recovery'):
        self.remote.request_recovery(HistoryResetRequired(f'Invalid camera timestamp: {age_ms:.3f}ms, frame={meta.frame_id}'))
      self.remote_started = False
      self.startup_good_frames = self.good_frames = 0
      self.last_eligible_at = None
      self.ever_qualified = self.recovering = False
      self.source, self.active, self.phase = 'local', self.local, 'reconnecting'
      # Drop this capture without replaying an older output or killing modeld.
      # The next valid capture can still run the permanently selected local model.
      self.output_context = None
      return None
    local_output, local_error = None, None
    local_elapsed, local_attempted, local_expired = 0., False, False

    def run_local():
      nonlocal local_output, local_error, local_elapsed, local_attempted, local_expired
      if local_attempted:
        return
      local_attempted = True
      local_started = self.clock()
      try:
        if not self._fresh(local_context):
          local_expired = True
          return
        local_output = self.local.run(*self._arguments_for(self.local, bufs, transforms, inputs, local_context))
        self.local_runs += 1
        if not self._valid(local_output):
          raise HostError('Local hot standby output is invalid')
        if not self._fresh(local_context):
          local_expired = True
          return
        local_elapsed = self.clock() - local_started
      except Exception as error:
        local_error = error
        raise

    remote_output = None
    events = []
    if self.phase != 'latched_local' and self.startup_good_frames >= 20:
      self.remote_started = True
      self.remote.submit_context = remote_context
      try:
        # QNN submits before invoking the callback, then polls after it. Run
        # local inference during phone execution, without a second QCOM thread.
        remote_output = self.remote.run(*self._arguments_for(self.remote, bufs, transforms, inputs, remote_context),
                                        after_enqueue=run_local)
        generation = getattr(self.remote, 'history_generation', 0)
        if generation != self.history_generation:
          self.history_generation = generation
          self.history_identity = self.last_remote_seq = self.last_remote_frame = None
          self.good_frames = 0
          self.last_eligible_at = None
          self.ever_qualified = self.recovering = False
        events = getattr(self.remote, 'completed_events', None)
        if events is None:
          raise HostError('Remote adapter lacks execution terminal accounting')
        self._account_completions(events, meta.frame_id)
        if remote_output is not None:
          remote_context = self.remote.output_context
          if not self._valid(remote_output):
            raise HostError('Remote output is invalid')
          if not events or events[-1]['frame_id'] != remote_context['meta_main'].frame_id:
            raise HostError('Remote completion accounting differs from selected output')
      except Exception as error:
        self._latch(error)
        remote_output = None
    if local_error is not None:
      self._latch(f'Local hot standby unavailable: {local_error}')
      raise local_error
    try:
      # Also cover a remote exception before submission or a latched session.
      run_local()
    except Exception as error:
      self._latch(f'Local hot standby unavailable: {error}')
      raise
    if local_expired:
      self.output_context = None
      return None
    # Remote preprocessing/socket work must not make the prepared local output
    # stale. A cached local result is not a valid fallback after a long stall.
    if not self._fresh(local_context):
      self.output_context = None
      return None
    now = self.clock()
    local_context, local_timing = action_context(local_output, local_context, now, self.action_target_tolerance)
    if local_context is None:
      self.output_context = None
      return None
    self.local_output, self.local_output_context, self.local_execution_time = local_output, local_context, local_elapsed
    try:
      local_action = candidate_action(self.local, local_output, local_context)
    except Exception as error:
      self._latch(f'Local candidate action is unavailable: {error}')
      raise HostError('No valid local action is available for hot standby') from error
    eligible, reason, remote_timing = False, 'remote_missing', None
    remote_action = None
    if remote_output is not None:
      if self._fresh(remote_context):
        remote_context, remote_timing = action_context(remote_output, remote_context, now, self.action_target_tolerance)
        if remote_context is None:
          reason = 'action_target_window'
        else:
          try:
            remote_action = candidate_action(self.remote, remote_output, remote_context)
            eligible, reason = compatible_actions(remote_action, local_action, context['v_ego'],
                                                  self.maximum_accel_difference, self.maximum_lateral_difference)
          except Exception as error:
            self._latch(f'Remote candidate action is invalid: {error}')
            reason = 'remote_action_invalid'
      else:
        reason = 'remote_expired'
    # Candidate parsing/comparison is real work too. Recheck at the routing
    # boundary rather than carrying a pre-comparison freshness verdict forward.
    if not self._fresh(local_context):
      self.output_context = None
      return None
    if eligible and not self._fresh(remote_context):
      eligible, reason = False, 'remote_expired_during_validation'
    now = self.clock()
    # An asynchronous connection may deliver zero completions this camera tick
    # and two next tick. Qualification belongs to checked new results, not to
    # scheduler ticks. Superseded heads were not compared, so count at most the
    # newest parsed candidate once. A missing tick still selects local below.
    completion_expired = any(event['terminal'] == 'expired' or
                             now - event['eof_ns'] / 1e9 >= self.maximum_age for event in events)
    eligible_gap = self.last_eligible_at is not None and now - self.last_eligible_at >= self.maximum_age
    candidate_failed = remote_output is not None and not eligible
    if completion_expired or eligible_gap or candidate_failed:
      self.good_frames = 0
      self.recovering = self.ever_qualified
      self.last_eligible_at = None
    if eligible:
      self.good_frames += 1
      self.last_eligible_at = now
    required = self.recovery_frames if self.ever_qualified else self.qualifying_frames
    candidate_ready = eligible and (not self.recovering and self.ever_qualified or self.good_frames >= required)
    if candidate_ready:
      self.ever_qualified, self.recovering = True, False
    candidate_phase = ('remote_active' if candidate_ready else
                       'recovering' if eligible and self.ever_qualified else
                       'local_bridge' if self.ever_qualified else 'qualifying')
    if getattr(self.remote, 'is_recovering', False):
      candidate_phase = 'reconnecting'
      reason = self.remote.recovery_reason
    ready = candidate_ready and self.allow_control and self.phase != 'latched_local'
    if ready:
      self.source, self.active, self.phase = 'qnn', self.remote, 'remote_active'
      output = remote_output
      self.output_context, self.output_execution_time = remote_context, self.remote.output_execution_time
    else:
      self.source, self.active = 'local', self.local
      output = local_output
      self.output_context, self.output_execution_time = local_context, local_elapsed
      if self.phase != 'latched_local':
        self.phase = candidate_phase if self.allow_control else 'shadow'
    self.handover_reason = reason if not candidate_ready else ''
    self.publish_seq += 1
    self.last_published_frame = self.output_context['meta_main'].frame_id
    self.last_published_context = self.output_context
    self.route_state = {'schema': 'qnn-route-v2', 'publish_seq': self.publish_seq, 'source': self.source,
      'source_frame_id': self.last_published_frame, 'source_eof_ns': self.output_context['meta_main'].timestamp_eof,
      'local_frame_id': meta.frame_id, 'local_eof_ns': meta.timestamp_eof,
      'source_age_ms': (self.clock() - self.output_context['meta_main'].timestamp_eof / 1e9) * 1000,
      'candidate_source': 'qnn' if candidate_ready else 'local', 'candidate_phase': candidate_phase,
      'phase': self.phase, 'reason': self.failure_reason if self.phase == 'latched_local' else self.handover_reason,
      'allow_control': self.allow_control, 'good_frames': self.good_frames, 'required_frames': required,
      'qualification_unit': 'checked_selected_results',
      'qualification_reset': ('expired_completion' if completion_expired else 'eligible_gap' if eligible_gap else
                              'candidate_failed' if candidate_failed else ''),
      'history_identity': self.history_identity, 'local_action_timing': local_timing, 'remote_action_timing': remote_timing}
    self.route_state['history_generation'] = self.history_generation
    self.route_state['local_action'] = {'curvature': float(local_action.desiredCurvature),
      'acceleration': float(local_action.desiredAcceleration), 'should_stop': bool(local_action.shouldStop)}
    if remote_action is not None:
      self.route_state['remote_action'] = {'curvature': float(remote_action.desiredCurvature),
        'acceleration': float(remote_action.desiredAcceleration), 'should_stop': bool(remote_action.shouldStop)}
    self._write_status()
    if after_enqueue:
      after_enqueue()
    return output

  def revalidate_publication(self, output, *, retime_plan=True):
    """Recheck after caller work without advancing histories or publish_seq.

    Call before action extraction with retime_plan=True. After messages have
    been filled use False: an already-computed action cannot be silently moved
    to a new target. If a different output/context is selected, the caller must
    rebuild its message or discard that publication, never send the old one.
    """
    now = self.clock()
    if self.local_output is None or not self._fresh(self.local_output_context):
      raise StaleLocalOutput('Local output expired at the publication boundary')
    local_context, local_timing = action_context(self.local_output, self.local_output_context, now,
                                               self.action_target_tolerance, retime_plan=retime_plan)
    if local_context is None:
      raise StaleLocalOutput('Local action target expired at the publication boundary')
    self.local_output_context = local_context
    selected_context = local_context
    if self.source == 'qnn':
      if self._fresh(self.output_context):
        selected_context, timing = action_context(output, self.output_context, now, self.action_target_tolerance,
                                                  retime_plan=retime_plan)
      else:
        selected_context, timing = None, None
      if selected_context is None:
        self.source, self.active = 'local', self.local
        self.phase = 'local_bridge' if self.allow_control else 'shadow'
        self.good_frames, self.recovering = 0, self.ever_qualified
        self.last_eligible_at = None
        self.handover_reason = 'publication_expired'
        output, selected_context = self.local_output, local_context
        self.output_execution_time = self.local_execution_time
        self.route_state.update(candidate_source='local', candidate_phase='local_bridge', reason='publication_expired',
                                good_frames=0, required_frames=self.recovery_frames)
      else:
        self.route_state['remote_action_timing'] = timing
    else:
      output = self.local_output
    self.output_context = selected_context
    self.last_published_context = selected_context
    self.last_published_frame = selected_context['meta_main'].frame_id
    self.route_state.update(source=self.source, phase=self.phase, source_frame_id=self.last_published_frame,
      source_eof_ns=selected_context['meta_main'].timestamp_eof,
      source_age_ms=(now - selected_context['meta_main'].timestamp_eof / 1e9) * 1000,
      local_action_timing=local_timing)
    # No status file I/O in the caller's final publication boundary. The next
    # regular tick exports the updated phase and in-memory route descriptor.
    return output, selected_context

  def get_action_from_model(self, *args):
    action = self.active.get_action_from_model(*args)
    self.route_state['published_action'] = {'curvature': float(action.desiredCurvature),
      'acceleration': float(action.desiredAcceleration), 'should_stop': bool(action.shouldStop)}
    return action

  def close(self):
    self.remote.close()
