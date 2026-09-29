"""Cinque v3 full-graph adapter: current images on wire, all graph history on phone."""
import os
import copy
import threading
import time

import numpy as np

from .session import AsyncSession
from .wire import HostError
from .faults import TransportUnavailable, HistoryResetRequired
from .qnn_reconnect import RecoveryWorker

SOURCE_SHA = '404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4'
BUNDLE_REF = 'c6d13eb723e0f6eee47ea7d56e47a700fba21380'
SLICES = {'lane_lines': (0, 528), 'lane_lines_prob': (528, 536), 'road_edges': (536, 800), 'meta': (800, 855),
          'desire_pred': (855, 887), 'pose': (887, 899), 'wide_from_device_euler': (899, 905), 'road_transform': (905, 917),
          'plan': (917, 1907), 'lead': (1907, 2051), 'lead_prob': (2051, 2054), 'desire_state': (2054, 2062),
          'action': (2062, 2066), 'hidden_state': (2066, 18450), 'pad': (18450, 18452)}


def validate_profile(profile, cam_w, cam_h):
  if profile.get('transport') != 'qnn_wifi':
    raise HostError('QNN adapter requires qnn_wifi transport')
  if profile.get('model_sha256') != SOURCE_SHA or profile.get('bundle_ref') != BUNDLE_REF:
    raise HostError('QNN source model or selected Cinque bundle identity differs')
  expected = (profile.get('capture_width'), profile.get('capture_height'))
  if any(type(value) is not int for value in expected) or expected != (cam_w, cam_h):
    raise HostError(f'QNN capture geometry mismatch: profile={expected[0]}x{expected[1]}, camera={cam_w}x{cam_h}')
  if (cam_w, cam_h) == (1344, 760):
    if os.getenv('C3XL_IFE_ROAD_SIZE') != '1344x760':
      raise HostError('QNN 1344x760 candidate requires the existing explicit IFE route')
    # modeld also requires the qualified CD210 dual-resolution local fallback.
    # Geometry acceptance enables shadow collection, not control qualification.
  elif (cam_w, cam_h) != (1928, 1208):
    raise HostError('QNN capture geometry is unsupported')
  if type(profile.get('allow_control', False)) is not bool:
    raise HostError('QNN allow_control must be an explicit boolean')
  runtime_sha = profile.get('runtime_model_sha256', '')
  if profile.get('allow_control') is True and profile.get('wire_protocol') != 'opif_tcp' and (not isinstance(runtime_sha, str) or len(runtime_sha) != 64 or
                                              any(c not in '0123456789abcdef' for c in runtime_sha)):
    raise HostError('QNN control requires a qualified, pinned runtime model hash')
  if not .05 <= float(profile.get('frame_delay_seconds', .1)) <= .15:
    raise HostError('QNN expected frame delay is not qualified')
  if not .05 <= float(profile.get('maximum_result_age_seconds', .2)) <= .2:
    raise HostError('QNN maximum result age must be 50 to 200 ms')


def encode_live_inputs(previous_desire, inputs, *, phone_desire_edges=False):
  desire = np.asarray(inputs['desire'], dtype=np.float32).reshape(8).copy()
  traffic = np.asarray(inputs['traffic_convention'], dtype=np.float32).reshape(2)
  action = np.asarray(inputs['action_t'], dtype=np.float32).reshape(2)
  if not all(np.isfinite(value).all() for value in (desire, traffic, action)):
    raise HostError('Nonfinite live QNN inputs')
  if not np.isin(desire, [0, 1]).all() or np.count_nonzero(desire) > 1:
    raise HostError('QNN caller desire must be one-hot or all zero')
  if not np.isin(traffic, [0, 1]).all() or np.count_nonzero(traffic) != 1:
    raise HostError('QNN traffic convention must be LHD [1,0] or RHD [0,1]')
  if (action < 0).any():
    raise HostError('QNN action horizons must be nonnegative')
  desire[0] = 0
  pulse = desire if phone_desire_edges else np.where(desire - previous_desire > .99, desire, 0)
  return np.concatenate((pulse, traffic, action)).astype('<f4').tobytes(), desire


def create_model(base_class, config_path, cam_w, cam_h, progress=None):
  from .qnn_cli import load_profile
  # QNN has its own explicit switch and per-drive failure latch. The loader
  # derives allow_control from the switch AND the verified qualification.
  profile = load_profile(config_path, require_enabled=True)
  validate_profile(profile, cam_w, cam_h)
  # This explicit phone profile selects Cinque independently of the local GPU
  # catalogue. validate_profile pins source SHA, semantic bundle and geometry;
  # OPIF START checks the model ABI; the parser below stays Cinque v3.
  # modeld separately loads and requires the actual local small-model runtime.
  from .qnn_client import connect_qnn
  from openpilot.sunnypilot.modeld_v2.modeld_base import ModelStateBase
  from openpilot.sunnypilot.modeld_v2.parse_model_outputs import Parser
  from openpilot.sunnypilot.models.split_model_constants import SplitModelConstants
  from openpilot.selfdrive.modeld.compile_modeld import NV12Frame, make_warp
  from openpilot.system.camerad.cameras.nv12_info import get_nv12_info
  from tinygrad import Tensor, TinyJit

  from openpilot.common.hardware import COMMA_HARDWARE
  from .wifi_power import WifiPowerLease
  radio = WifiPowerLease() if COMMA_HARDWARE else None
  link = None
  health = startup_error = None
  try:
    initial = dict(profile, connect_timeout=.5) if profile.get('wire_protocol') == 'opif_tcp' else profile
    link = connect_qnn(initial, client_role='modeld' if profile.get('allow_control') is True else 'shadow')
    health = link.hello(timeout=1 if profile.get('wire_protocol') == 'opif_tcp' else 5)
  except TransportUnavailable as error:
    startup_error = error
    if link is not None:
      link.close()
    link = None
  except Exception:
    try:
      if link is not None:
        link.close()
    finally:
      if radio is not None:
        radio.close()
    raise

  class QnnModel(base_class):
    external_host = True
    qnn_remote = True
    host_name = 'android_qnn'

    def __init__(self):
      ModelStateBase.__init__(self)
      self.profile = profile
      # Pin the exact endpoint/model/schema for the lifetime of this adapter.
      self._recovery_profile = copy.deepcopy(profile)
      self.health = health
      self.history_generation = 0
      self._recovery = None
      self._closed = False
      self.recovery_reason = ''
      self.chestnut, self.generation = True, 12
      self.model_ref, self.model_artifact_sha = BUNDLE_REF, SOURCE_SHA
      self.LAT_SMOOTH_SECONDS, self.LONG_SMOOTH_SECONDS = 0., .3
      self.MIN_LAT_CONTROL_SPEED, self.PLANPLUS_CONTROL = .3, 1.
      self.constants, self.parser = SplitModelConstants(), Parser()
      self._vision_input_names, self._desire_key = ['img', 'big_img'], 'desire'
      self.numpy_inputs = {'desire': np.zeros(8, np.float32), 'traffic_convention': np.zeros(2, np.float32), 'action_t': np.zeros(2, np.float32)}
      self.prev_desire = np.zeros(8, np.float32)
      self.expected_frame_delay = float(profile.get('frame_delay_seconds', .1))
      self.submit_context = self.output_context = None
      self.completed_samples = []
      self.completed_events = []
      self.expired_outputs = 0
      self.output_execution_time = 0.
      self.owner_thread = None
      stride, yh, uvh, size = get_nv12_info(cam_w, cam_h)
      self.frame_size, self.blobs = size, {}
      # Shared DEVICE_CAMERAS intrinsics already account for IFE scaling.
      # Consume modeld's transforms directly; never add another resize matrix.
      base = make_warp(NV12Frame(cam_w, cam_h, stride, yh, uvh, size), 512, 256)
      self.warp = TinyJit(lambda tfm, big_tfm, frame, big_frame: base(tfm, big_tfm, frame, big_frame).realize())
      # Warm the same borrowed-host-buffer mapping used by VisionIPC. Warming
      # only GPU-owned buffers leaves Tinygrad's CPU dcache-flush compiler cold
      # until the first camera frame, consuming its publication deadline.
      self._warmup_host_frames = [np.zeros(size, np.uint8) for _ in range(2)]
      dummy = [Tensor.from_blob(frame.ctypes.data, (size,), dtype='uint8', device='QCOM')
               for frame in self._warmup_host_frames]
      tfms = [Tensor(np.eye(3, dtype=np.float32), device='NPY').realize() for _ in range(2)]
      for _ in range(3):
        self.warp(*tfms, *dummy).numpy()
      self.async_session = (AsyncSession(link, float(profile.get('maximum_result_age_seconds', .2)), warming_up=True)
                            if link is not None else None)
      if startup_error is not None:
        self.request_recovery(startup_error)
      if progress:
        progress(95)

    def close(self):
      # A failure is handled on modeld's frame loop. Joining network threads
      # here would age out the already-computed hot local result.
      try:
        self._closed = True
        if self._recovery is not None:
          self._recovery.close()
        if self.async_session is not None:
          self.async_session.close(wait=False)
          self.async_session.link.close(wait=False)
        self.prev_desire[:] = 0
      finally:
        if radio is not None:
          radio.close()

    @property
    def is_recovering(self):
      return self._recovery is not None

    def _connect_replacement(self):
      from .qnn_discoveryd import usb_endpoint, hotspot_endpoint
      profile = self._recovery_profile
      endpoints = [endpoint['host'] for endpoint in (usb_endpoint(profile), hotspot_endpoint(profile)) if endpoint]
      endpoints.append(profile['host'])
      last_error = None
      for host in dict.fromkeys(endpoints):
        replacement = None
        try:
          replacement = connect_qnn(dict(profile, host=host, connect_timeout=0.5),
                                    client_role='modeld' if profile.get('allow_control') is True else 'shadow')
          replacement_health = replacement.hello(timeout=1)
          maximum_age = self.async_session.maximum_age if self.async_session is not None else float(profile.get('maximum_result_age_seconds', .2))
          session = AsyncSession(replacement, maximum_age, warming_up=True)
          self.recovery_reason = ''
          replacement = None  # AsyncSession now owns the live link.
          return session, replacement_health
        except TransportUnavailable as error:
          last_error = error
        finally:
          if replacement is not None:
            replacement.close(wait=False)
      raise last_error or TransportUnavailable('Bound phone has no current USB or hotspot endpoint')

    def request_recovery(self, reason):
      if not isinstance(reason, (TransportUnavailable, HistoryResetRequired)):
        raise HostError('Only typed transport/history faults permit session recovery')
      if self._closed:
        raise HostError('Closed QNN adapter cannot recover')
      if self._recovery is not None:
        return
      self.recovery_reason = str(reason)
      self.output_context = None
      self.completed_events = []
      if self.async_session is not None:
        try:
          self.async_session.close(wait=False)
        finally:
          self.async_session.link.close(wait=False)
      self._recovery = RecoveryWorker(self._connect_replacement)

    def run(self, bufs, transforms, inputs, after_enqueue=None):
      thread = threading.get_ident()
      if self.owner_thread is None:
        self.owner_thread = thread
      if thread != self.owner_thread:
        raise HostError('QNN camera preprocessing changed modeld threads')
      context = self.submit_context
      if context is None:
        raise HostError('QNN model needs matching capture publication context')
      meta = context['meta_main']
      try:
        if self._closed:
          raise HostError('QNN adapter is closed')
        if self._recovery is not None:
          ready, error = self._recovery.take()
          if error is not None:
            raise error
          if ready is None:
            self.completed_events = []
            self.output_context = None
            if after_enqueue:
              after_enqueue()
            return None
          self.async_session, self.health = ready
          self._recovery = None
          self.history_generation += 1
          self.prev_desire[:] = 0
          self.completed_events = []
        age = (time.clock_gettime_ns(time.CLOCK_BOOTTIME) - meta.timestamp_eof) / 1e9
        if not 0 <= age < self.async_session.maximum_age:
          raise HostError('QNN camera input exceeded the deadline')
        self.completed_samples = []
        self.completion_wait_seconds = 0.
        self.completed_events = []
        def take_completed():
          item = self.async_session.poll(timeout=0.)
          if item is not None:
            output, capture, _, stats = item
            checked_at = time.clock_gettime(time.CLOCK_BOOTTIME)
            output_eof = capture['meta_main'].timestamp_eof / 1e9
            values = np.frombuffer(output, dtype='<f4')
            schema = stats.get('result_schema', 'full_f32')
            expected = {'full_f32': 18452, 'control_heads_f32': 2068}.get(schema)
            if expected is None or values.size != expected or not np.isfinite(values).all():
              raise HostError('QNN completed response is invalid')
            if not 0 <= checked_at - output_eof < self.async_session.maximum_age:
              self.expired_outputs += 1
              return None
            self.completed_samples.append((capture, checked_at))
          return item
        def drain():
          newest = None
          # poll may consume expired entries itself. Capacity bounds every pass.
          for _ in range(self.async_session.capacity):
            item = take_completed()
            if item is not None:
              newest = item
          return newest
        # Release already-completed transport slots before preprocessing/local
        # work. Never let an expired publication terminate valid graph history.
        completed = drain()
        buffers = []
        for name in self._vision_input_names:
          data = np.frombuffer(bufs[name].data, dtype=np.uint8)
          if data.size < self.frame_size:
            raise HostError('Truncated QNN VisionIPC image')
          key = (name, data.ctypes.data)
          if key not in self.blobs:
            self.blobs[key] = Tensor.from_blob(data.ctypes.data, (self.frame_size,), dtype='uint8', device='QCOM')
          buffers.append(self.blobs[key])
        tfms = [Tensor(np.ascontiguousarray(transforms[key], dtype=np.float32), device='NPY').realize() for key in self._vision_input_names]
        pixels = np.ascontiguousarray(self.warp(*tfms, *buffers).numpy(), dtype=np.uint8)
        if pixels.shape != (2, 6, 128, 256):
          raise HostError('QNN Cinque packed6 ABI differs')
        scalars, next_desire = encode_live_inputs(self.prev_desire, inputs, phone_desire_edges=self.profile.get('wire_protocol') == 'opif_tcp')
        if (time.clock_gettime_ns(time.CLOCK_BOOTTIME) - meta.timestamp_eof) / 1e9 >= self.async_session.maximum_age:
          raise HostError('QNN preprocessing exceeded the capture deadline')
        self.async_session.submit(meta.frame_id, meta.timestamp_eof, pixels.tobytes(), scalars, context)
        self.prev_desire[:] = next_desire
        if after_enqueue:
          after_enqueue()
        newer = drain()
        if newer is not None:
          completed = newer
        self.completed_events = self.async_session.drain_events()
        if completed is None:
          self.output_context = None
          return None
        output, self.output_context, self.output_execution_time, stats = completed
        if self.profile.get('wire_protocol') == 'opif_tcp':
          # Preserve the actual capture metadata and add transport provenance.
          self.output_context = dict(self.output_context, opif_session_id=stats['opif_session_id'],
            opif_state_epoch=stats['state_epoch'], opif_request_id=stats['request_id'])
        age = (time.clock_gettime_ns(time.CLOCK_BOOTTIME) - self.output_context['meta_main'].timestamp_eof) / 1e9
        if not 0 <= age < self.async_session.maximum_age:
          self.expired_outputs += 1
          self.output_context = None
          return None
        raw = np.frombuffer(output, dtype='<f4').copy()
        self.async_session.warming_up = False
        if stats.get('result_schema', 'full_f32') == 'control_heads_f32':
          # Compact results explicitly omit hidden_state; never fabricate zeros
          # and never reinterpret a compact buffer as the original full ABI.
          heads = {key: raw[np.newaxis, slice(*bounds)] for key, bounds in SLICES.items() if bounds[1] <= 2066}
          heads['pad'] = raw[np.newaxis, 2066:2068]
        else:
          heads = {key: raw[np.newaxis, slice(*bounds)] for key, bounds in SLICES.items()}
        # Cinque stores ALL 72 lead means followed by ALL 72 log stds. Generic
        # MDN inference would interpret three alternating mu24/std24 blocks.
        lead = heads.pop('lead')
        parsed = self.parser.parse_outputs(heads)
        parsed['lead'] = lead
        self.parser.parse_mdn('lead', parsed, out_shape=(3, 6, 4), in_N=1)
        return parsed
      except (TransportUnavailable, HistoryResetRequired) as error:
        self.request_recovery(error)
        if after_enqueue:
          after_enqueue()
        return None
      except Exception:
        self.close()
        raise

  try:
    return QnnModel()
  except Exception:
    try:
      link.close()
    finally:
      if radio is not None:
        radio.close()
    raise
