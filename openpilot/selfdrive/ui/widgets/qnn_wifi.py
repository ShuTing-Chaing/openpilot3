"""Nonblocking UI facade for QNN Wi-Fi pairing and descriptive runtime state.

Authorization remains in the model/runtime. Nothing read from the status JSON
can grant control. Credentials are handled exclusively by qnn_cli.
"""
import json
import ipaddress
import math
import os
import queue
import re
import threading
import time
from pathlib import Path

ENABLED_PARAM = "C3XLQnnWifiEnabled"
CONTROL_PARAM = "C3XLQnnWifiControl"
EXECUTION_MODES = ("npu_only", "npu_cpu", "gpu_cpu", "cpu")
ICON = "icons/network.png"
STATUS_PATH = Path("/dev/shm/qnn-host-status.json")
PHASE_LABELS = {"shadow": "shadow / local model", "qualifying": "qualifying / local model",
                "handover_wait": "local / awaiting newer remote output",
                "remote_active": "remote output selected", "latched_local": "local fallback locked"}
PAIRING_STEPS = (
  ("1. Phone", "Join the same Wi-Fi. Start the Android inference service and open its temporary pairing window."),
  ("2. Discover", "Choose Discover phones or enter the IPv4 address manually. A discovered phone is not trusted yet."),
  ("3. Pair", "Compare all 64 fingerprint digits with the phone, confirm the match, then enter its temporary pairing code."),
  ("4. Configure", "Pairing stores private credentials and an active profile. Forget removes local trust; use the phone app to revoke server-side access."),
  ("5. Shadow first", "Enable Wi-Fi shadow mode offroad. Control stays off until separate device/model/source qualification is verified."),
)


def _text(value, limit=128):
  if not isinstance(value, str):
    return ""
  return " ".join(value.split())[:limit]


def _runtime_status():
  try:
    with STATUS_PATH.open() as stream:
      raw = stream.read(65537)
    if len(raw) > 65536:
      return {}
    status = json.loads(raw)
    if not isinstance(status, dict) or status.get("schema") != "qnn-host-status-v1":
      return {}
    updated = status.get("updated_boottime")
    now = time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else time.monotonic()
    if not isinstance(updated, (int, float)) or not math.isfinite(updated) or not 0 <= now - updated <= 3:
      return {}
    # Only descriptive, bounded values leave this function. Never forward raw errors/config.
    clean = {"updated_boottime": updated, "source": status.get("source") if status.get("source") in ("local", "qnn") else "unknown",
             "phase": status.get("phase") if status.get("phase") in PHASE_LABELS else "unknown"}
    for key in ("good_frames", "qualification_frames", "local_runs", "remote_outputs"):
      value = status.get(key)
      clean[key] = value if type(value) is int and 0 <= value < 10**12 else None
    clean["failed"] = bool(status.get("failure_reason"))
    reason = str(status.get("failure_reason", "")).lower()
    clean["auth_failed"] = any(word in reason for word in ("auth", "credential", "certificate", "fingerprint", "pairing"))
    return clean
  except (OSError, ValueError, TypeError):
    return {}


def _load(profile_path=None):
  try:
    # Deferred import supports staged rollouts without importing model/NPU code in UI.
    from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import status
    source = status() if profile_path is None else status(profile_path)
    if not isinstance(source, dict):
      raise ValueError("invalid status schema")
    public = {"paired": source.get("paired") is True,
              "configured": source.get("configured") is True or source.get("paired") is True,
              "wire_protocol": _text(source.get("wire_protocol")),
              "control_qualified": source.get("control_qualified") is True,
              "control_preference": source.get("control_preference") is True,
              "auth_error": bool(source.get("auth_error")),
              "endpoint": _text(source.get("endpoint")), "device_id": _text(source.get("device_id")),
              "qualification_reason": _text(source.get("qualification_reason"), 160),
              "execution_mode": source.get("execution_mode") if source.get("execution_mode") in EXECUTION_MODES else ""}
    fingerprint = source.get("fingerprint_sha256", "")
    public["fingerprint_sha256"] = fingerprint.lower() if isinstance(fingerprint, str) and re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint) else ""
    public["api_available"] = True
  except Exception:
    # Exceptions may contain credential-bearing paths/arguments. Do not log/display them.
    public = {"paired": False, "control_qualified": False, "auth_error": False, "api_available": False}
  runtime = _runtime_status()
  if runtime.get("auth_failed"):
    public["auth_error"] = True
  return public, runtime


class QnnWifiUiState:
  def __init__(self, params, is_offroad, profile_path=None):
    self.params, self.is_offroad, self.profile_path = params, is_offroad, profile_path
    self.public, self.runtime = {}, {}
    self.message = ""
    self._worker = None
    self._next_poll = 0.
    self._results = queue.SimpleQueue()
    self._request = None
    self._generation = 0
    self.pairing = QnnPairingController(self, profile_path=profile_path)

  def flag(self, key):
    if key == CONTROL_PARAM:
      return self.public.get("control_preference") is True
    try:
      return self.params.get(key, return_default=True) is True
    except Exception:
      return False

  @property
  def paired(self):
    return self.public.get("paired") is True and not self.public.get("auth_error")

  @property
  def configured(self):
    return (self.public.get("configured") is True or self.public.get("paired") is True) and not self.public.get("auth_error")

  @property
  def control_preference_editable(self):
    return self.configured

  @property
  def control_available(self):
    return self.paired and self.public.get("control_qualified") is True and self.flag(ENABLED_PARAM)

  @property
  def pending(self):
    return self._request is not None

  def request(self, key, value):
    if key not in (ENABLED_PARAM, CONTROL_PARAM) or not self.is_offroad():
      self.message = "Changes require offroad."
      return
    self._generation += 1
    self._request = (self._generation, key, bool(value))
    self.message = "Checking pairing and qualification..."
    self._next_poll = 0.

  def update(self):
    while not self._results.empty():
      public, runtime, request = self._results.get_nowait()
      self.public, self.runtime = public, runtime
      if request is not None and request == self._request:
        self._request = None
        _, key, value = request
        if key == CONTROL_PARAM:
          if public.pop("_control_saved", False):
            self.message = "Preference saved across restarts and drives."
            if value and not self.control_available:
              self.message += " Not active: " + ("phone inference is disabled; " if not self.flag(ENABLED_PARAM) else "") + (self.public.get("qualification_reason") or "verification required")
            elif value:
              self.message += " Applied at the next model startup after runtime checks."
          else:
            self.message = "Not saved: changes require offroad and a valid phone profile."
        elif not self.is_offroad():
          self.message = "Refused: vehicle is no longer offroad."
        elif value and not self.configured:
          self.message = "Refused: pairing or control qualification is missing."
        else:
          try:
            # Writes run on the UI thread after a fresh background validation and
            # an offroad recheck. Runtime independently validates all authority.
            if key == ENABLED_PARAM and not value:
              self.params.put_bool(CONTROL_PARAM, False, block=True)
            self.params.put_bool(key, value, block=True)
            self.message = "Saved for next drive."
          except Exception:
            self.message = "Setting unavailable: update the Params definitions."
    now = time.monotonic()
    if (self._worker is None or not self._worker.is_alive()) and now >= self._next_poll:
      request = self._request
      self._next_poll = now + 1

      def read():
        public, runtime = _load(self.profile_path)
        if request is not None and request == self._request and request[1] == CONTROL_PARAM:
          try:
            from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import set_control_preference, PROFILE
            set_control_preference(request[2], self.profile_path or PROFILE, params=self.params, offroad_check=self.is_offroad)
            public, runtime = _load(self.profile_path)
            public["_control_saved"] = True
          except Exception:
            public["_control_saved"] = False
        self._results.put((public, runtime, request))

      self._worker = threading.Thread(target=read, name="qnn-ui-status", daemon=True)
      self._worker.start()

  def _live_runtime(self):
    now = time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else time.monotonic()
    updated = self.runtime.get("updated_boottime")
    return self.runtime if isinstance(updated, (int, float)) and 0 <= now - updated <= 3 else {}

  def summary(self):
    if self.pending:
      return "checking configuration"
    if not self.public.get("api_available"):
      return "configuration unavailable"
    if self.public.get("auth_error"):
      return "authentication failed"
    if self.public.get("wire_protocol") == "opif_tcp" and self.configured:
      return "OPIF TCP / shadow only" if self.flag(ENABLED_PARAM) else "OPIF TCP / disabled"
    if not self.paired:
      return "not paired"
    if not self.flag(ENABLED_PARAM):
      return "disabled / paired"
    runtime = self._live_runtime()
    if not runtime:
      return "paired / status stale"
    return PHASE_LABELS.get(runtime.get("phase"), "runtime unknown")

  def rows(self):
    runtime = self._live_runtime()
    source = {"qnn": "Android remote", "local": "C3XL local model"}.get(runtime.get("source"), "unknown / status stale")
    return [
      ("Snapdragon / QNN", self.summary()),
      ("Phone endpoint", self.public.get("endpoint") or "not configured"),
      ("Device identity", self.public.get("device_id") or "not available"),
      ("Profile execution mode", self.public.get("execution_mode") or "not configured"),
      ("Pairing", "OPIF: unauthenticated endpoint" if self.public.get("wire_protocol") == "opif_tcp" else ("credentials configured" if self.paired else "not paired / authentication failed")),
      ("Selected output", source),
      ("Runtime phase", PHASE_LABELS.get(runtime.get("phase"), "unknown / status stale")),
      ("Local frames", str(runtime.get("local_runs") if runtime.get("local_runs") is not None else "not available")),
      ("Remote outputs", str(runtime.get("remote_outputs") if runtime.get("remote_outputs") is not None else "not available")),
      ("Control preference", "ON / saved across restarts" if self.flag(CONTROL_PARAM) else "OFF / saved"),
      ("Control eligibility", "available at model startup" if self.control_available else "blocked; see verification detail"),
      ("Control qualification", "separate artifact verified" if self.public.get("control_qualified") else "not qualified"),
      ("Qualification detail", self.public.get("qualification_reason") or "No source/model/device-bound qualification evidence."),
      ("Latest UI action", self.message or "No change requested."),
    ]


class QnnPairingController:
  """Native UI handlers. Public state only; credentials stay inside qnn_cli."""
  def __init__(self, state, profile_path=None):
    self.state, self.profile_path = state, profile_path
    self.devices = []
    self.selection = None
    self.fingerprint_confirmed = False
    self.capture = (1344, 760) if os.getenv('C3XL_IFE_ROAD_SIZE') == '1344x760' else (1928, 1208)
    self.execution_mode = "npu_only"
    self.message = "Discover a phone or enter its IPv4 address."
    self.last_action, self.last_outcome = '', ''
    self._worker = None
    self._waiting = False
    self._results = queue.SimpleQueue()

  @property
  def busy(self):
    return self._waiting

  def _allowed(self):
    if not self.state.is_offroad():
      self.message = "Changes require offroad."
      return False
    if self.busy or self.state.pending:
      self.message = "Wait for the current operation."
      return False
    return True

  def _launch(self, action, function):
    if not self._allowed():
      return False
    self._waiting = True
    self.last_action, self.last_outcome = action, 'pending'
    self.message = {'discover': 'Looking for phones...', 'pair': 'Pairing over verified TLS...', 'forget': 'Removing local trust...',
                    'opif': 'Saving OPIF TCP endpoint...', 'mode': 'Saving local execution mode...'}[action]

    def work():
      try:
        if not self.state.is_offroad():
          raise RuntimeError('Offroad ended')
        result = function()
        self._results.put((action, True, result))
      except Exception:
        # No raw peer error or credential-bearing exception reaches UI/logs.
        self._results.put((action, False, {}))
    self._worker = threading.Thread(target=work, name='qnn-ui-pairing', daemon=True)
    self._worker.start()
    return True

  def begin_discovery(self):
    def discover():
      from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import discover
      return discover(timeout=3)
    return self._launch('discover', discover)

  def select_endpoint(self, endpoint, advertised_pin=''):
    if not self._allowed():
      return False
    self.fingerprint_confirmed = False
    try:
      fields = str(endpoint).strip().split(':')
      if not 1 <= len(fields) <= 2:
        raise ValueError('IPv4 endpoint expected')
      host = str(ipaddress.IPv4Address(fields[0]))
      port = int(fields[1]) if len(fields) == 2 else 5600
      if not 1 <= port <= 65535:
        raise ValueError('Port outside bounds')
      self.selection = {'host': host, 'port': port, 'fingerprint': ''}
      if advertised_pin:
        self.set_fingerprint(advertised_pin)
      self.message = 'Compare the complete fingerprint with the phone.'
      return True
    except ValueError:
      self.selection = None
      self.message = 'Enter IPv4 or IPv4:port, for example 172.16.1.129:5600.'
      return False

  def set_fingerprint(self, fingerprint):
    self.fingerprint_confirmed = False
    if not self._allowed() or self.selection is None:
      return False
    clean = re.sub(r'[\s:]', '', str(fingerprint)).lower()
    if not re.fullmatch(r'[a-f0-9]{64}', clean):
      self.selection['fingerprint'] = ''
      self.message = 'Enter all 64 hexadecimal digits shown by the phone.'
      return False
    self.selection['fingerprint'] = clean
    return True

  def confirm_fingerprint(self):
    if not self._allowed() or self.selection is None or not self.selection.get('fingerprint'):
      return False
    self.fingerprint_confirmed = True
    return True

  def begin_pair(self, code):
    if not self._allowed() or not self.fingerprint_confirmed or self.selection is None:
      self.message = 'Compare and confirm the full phone fingerprint first.'
      return False
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
      self.message = 'Enter the six-digit code from the open phone pairing window.'
      return False
    selected, capture, mode = dict(self.selection), self.capture, self.execution_mode
    def save():
      from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import pair_and_save, PROFILE
      return pair_and_save(selected['host'], selected['port'], selected['fingerprint'], code,
                           path=self.profile_path or PROFILE, params=self.state.params, offroad_check=self.state.is_offroad,
                           capture_width=capture[0], capture_height=capture[1], execution_mode=mode)
    return self._launch('pair', save)

  def select_execution_mode(self, mode):
    if not self._allowed() or mode not in EXECUTION_MODES:
      return False
    self.execution_mode = mode
    self.message = 'Mode selected only. Apply to the local profile explicitly; set the same mode on the phone.'
    return True

  def cycle_execution_mode(self):
    return self.select_execution_mode(EXECUTION_MODES[(EXECUTION_MODES.index(self.execution_mode) + 1) % len(EXECUTION_MODES)])

  def begin_opif(self, endpoint):
    if not self._allowed():
      return False
    try:
      fields = endpoint.strip().split(':')
      host = str(ipaddress.IPv4Address(fields[0]))
      port = int(fields[1]) if len(fields) == 2 else 5555
      if len(fields) > 2 or not 1 <= port <= 65535:
        raise ValueError('Invalid endpoint')
    except (ValueError, TypeError):
      self.message = 'Enter a phone IPv4 address or IPv4:5555.'
      return False
    capture = self.capture
    def save():
      from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import configure_opif, PROFILE
      return configure_opif(host, port, path=self.profile_path or PROFILE, params=self.state.params,
                            offroad_check=self.state.is_offroad, capture_width=capture[0], capture_height=capture[1])
    return self._launch('opif', save)

  def begin_mode_update(self):
    mode = self.execution_mode
    def save_mode():
      from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import set_execution_mode, PROFILE
      return set_execution_mode(mode, self.profile_path or PROFILE, params=self.state.params, offroad_check=self.state.is_offroad)
    return self._launch('mode', save_mode)

  def begin_forget(self):
    def forget():
      from openpilot.sunnypilot.modeld_v2.external_host.qnn_cli import forget_pairing, PROFILE
      return forget_pairing(self.profile_path or PROFILE, params=self.state.params, offroad_check=self.state.is_offroad)
    return self._launch('forget', forget)

  def poll(self):
    self.state.update()
    while not self._results.empty():
      action, success, result = self._results.get_nowait()
      self._waiting = False
      self.last_action, self.last_outcome = action, 'ok' if success else 'failed'
      if not success:
        self.message = 'Not saved. Check offroad, phone pin/code and window. Forget an old local profile before re-pairing.'
        continue
      if action == 'discover':
        self.devices = []
        for item in result.get('devices', [])[:12]:
          try:
            host, port = str(ipaddress.IPv4Address(item['host'])), int(item['port'])
            if not 1 <= port <= 65535:
              continue
            pin = _text(item.get('advertised_fingerprint'))
            self.devices.append({'name': _text(item.get('name'), 64) or 'QNN phone', 'host': host, 'port': port,
                                 'fingerprint': pin if re.fullmatch(r'[a-fA-F0-9]{64}', pin) else ''})
          except (TypeError, ValueError, KeyError):
            continue
        self.message = (f'{len(self.devices)} untrusted candidate(s). Compare the phone fingerprint.' if self.devices else
                        'No phones discovered. Use manual IPv4; check Wi-Fi and the Android service.')
      elif action == 'mode':
        self.state.public = dict(result, api_available=True)
        self.message = 'Profile mode saved; enable/control are off. Select the SAME mode in the phone app.'
      elif action == 'opif':
        self.state.public = dict(result, api_available=True)
        self.message = 'OPIF TCP configured for either App. Unauthenticated; shadow only. Enable remains off.'
      elif action == 'pair':
        self.state.public = dict(result, api_available=True)
        self.message = 'Paired. Wi-Fi and control remain off until explicitly enabled.'
      else:
        self.state.public = {'paired': False, 'control_qualified': False, 'api_available': True}
        self.selection, self.fingerprint_confirmed = None, False
        self.message = 'Local pairing forgotten. Use the phone app to revoke its saved client authorization.'
      self.state._next_poll = 0.
