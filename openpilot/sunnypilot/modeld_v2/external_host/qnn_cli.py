"""Offline profile gates and discovery for QNN hosts."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .qnn_client import CINQUE_SHA, QnnError, connect_qnn, pair

PROFILE = Path('/data/qnn-host/active-host.json')
BUNDLE_REF = 'c6d13eb723e0f6eee47ea7d56e47a700fba21380'
HEX = re.compile(r'^[0-9a-f]{64}$')
EXECUTION_MODES = ('npu_only', 'npu_cpu', 'gpu_cpu', 'cpu')


def _read(path):
  path = Path(path)
  if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
    raise QnnError('Missing or unsafe QNN configuration file')
  data = json.loads(path.read_text())
  if not isinstance(data, dict):
    raise QnnError('QNN configuration must be an object')
  return data


def _params(params=None):
  if params is not None:
    return params
  from openpilot.common.params import Params

  return Params()


def _qualification(profile):
  """A readiness flag is never a control qualification certificate."""
  if not profile.get('qualification_file'):
    return False, '尚无独立的后端执行、精度、热备与持续性能资格记录'
  try:
    q = _read(profile['qualification_file'])
    if q.get('schema') != 1 or q.get('qualified') is not True:
      return False, '资格记录尚未通过'
    fields = ('model_sha256', 'capture_width', 'capture_height', 'execution_mode')
    if profile.get('wire_protocol') != 'opif_tcp':
      fields += ('runtime_model_sha256', 'runtime_artifact_sha256', 'device_id', 'fingerprint_sha256')
    for field in fields:
      if not profile.get(field) or q.get(field) != profile[field]:
        return False, '资格记录与当前模型或采集配置不一致'
    mode = profile.get('execution_mode')
    if mode not in EXECUTION_MODES:
      return False, '资格记录缺少明确支持的执行模式'
    placement = 'npu_htp_verified' if mode == 'npu_only' else 'backend_execution_verified'
    for field in (placement, 'outputs_verified', 'hotstandby_verified', 'sustained_timing_verified'):
      if q.get(field) is not True:
        return False, '资格记录缺少必要的端到端验证'
    artifact = Path(q['artifact_manifest'])
    if (
      not artifact.is_file()
      or artifact.is_symlink()
      or artifact.stat().st_size > 65536
      or not HEX.fullmatch(q.get('artifact_sha256', ''))
      or hashlib.sha256(artifact.read_bytes()).hexdigest() != q['artifact_sha256']
    ):
      return False, '资格证据清单哈希不匹配'
    sources = q.get('source_files')
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 32:
      return False, '资格记录未绑定实际源文件'
    repo = Path(__file__).resolve().parents[4]
    for relative, sha in sources.items():
      file = (repo / relative).resolve()
      if (
        not file.is_relative_to(repo)
        or not file.is_file()
        or file.stat().st_size > 2 * 1024 * 1024
        or not HEX.fullmatch(sha)
        or hashlib.sha256(file.read_bytes()).hexdigest() != sha
      ):
        return False, '代码已变化，需重新资格验证'
    return True, '后端、输出、热备、时延和源文件资格记录已核对'
  except (OSError, ValueError, KeyError, TypeError):
    return False, '资格记录不可用或格式错误'


def load_profile(path=PROFILE, require_enabled=False):
  profile = _read(path)
  if profile.get('transport') != 'qnn_wifi' or profile.get('model_sha256') != CINQUE_SHA:
    raise QnnError('Profile is not the pinned Cinque v3 QNN Wi-Fi model')
  geometry = (profile.get('capture_width'), profile.get('capture_height'))
  if any(type(value) is not int for value in geometry) or geometry not in ((1928, 1208), (1344, 760)):
    raise QnnError('Explicit supported capture geometry is required')
  profile['host'] = str(ipaddress.IPv4Address(profile['host']))
  profile['port'] = int(profile.get('port', (5555 if profile.get('wire_protocol')=='opif_tcp' else 5600)))
  protocol = profile.get('wire_protocol', 'nqw2_tls')
  if protocol not in ('nqw2_tls', 'opif_tcp') or not 1 <= profile['port'] <= 65535:
    raise QnnError('Invalid phone endpoint or wire protocol')
  if protocol == 'opif_tcp':
    if profile.get('transport_authenticated') is not False or profile.get('allow_control') is not False:
      raise QnnError('OPIF stores no transport authentication or effective control grant')
  if protocol != 'opif_tcp':
    if not HEX.fullmatch(profile.get('fingerprint_sha256', '')):
      raise QnnError('Invalid QNN certificate fingerprint')
    credentials = _read(profile['pairing_file'])
    if not isinstance(credentials.get('client_id'), str) or not HEX.fullmatch(credentials.get('token', '')):
      raise QnnError('Invalid saved QNN pairing')
    if credentials.get('device_id') != profile.get('device_id') or not profile.get('device_id'):
      raise QnnError('QNN device identity differs from pairing')
  mode = profile.get('execution_mode', 'npu_only')
  if mode not in EXECUTION_MODES:
    raise QnnError('Unknown QNN execution mode')
  preference = profile.get('prefer_control', False)
  if type(preference) is not bool:
    raise QnnError('Control preference must be a boolean')
  qualified, reason = _qualification(profile)
  profile['execution_mode'] = mode  # Effective legacy default only; never rewrite on read.
  enabled = requested = failed = False
  try:
    params = _params()
    enabled = params.get_bool('C3XLQnnWifiEnabled')
    requested = preference or params.get_bool('C3XLQnnWifiControl')
    failed = params.get_bool('C3XLQnnWifiFailedThisOnroad')
  except Exception as e:
    if require_enabled:
      raise QnnError('QNN runtime Params are unavailable') from e
  if require_enabled:
    from .opt_in import on_target_branch

    if not on_target_branch():
      raise QnnError('QNN Wi-Fi is restricted to C3XL hardware')
  if require_enabled and (not enabled or failed):
    raise QnnError('QNN is disabled or latched off for this drive')
  profile['control_preference'] = preference
  profile['allow_control'] = bool(enabled and requested and qualified and not failed)
  profile['control_qualified'] = qualified
  profile['qualification_reason'] = reason
  return profile


def status(path=PROFILE):
  """Bounded file-only UI status. Paired means saved trust, not a live connection."""
  output = {
    'paired': False,
    'endpoint': '',
    'device_id': '',
    'fingerprint_sha256': '',
    'control_qualified': False,
    'qualification_reason': '尚未配对',
    'auth_error': False,
    'execution_mode': '',
  }
  try:
    profile = load_profile(path)
    output.update(
      paired=profile.get('wire_protocol') != 'opif_tcp',
      configured=True, wire_protocol=profile.get('wire_protocol', 'nqw2_tls'),
      execution_mode=profile['execution_mode'],
      endpoint=f"{profile['host']}:{profile['port']}",
      device_id=profile.get('device_id', ''),
      fingerprint_sha256=profile.get('fingerprint_sha256', '') if profile.get('wire_protocol') != 'opif_tcp' else '',
      control_qualified=profile['control_qualified'],
      control_preference=profile['control_preference'],
      qualification_reason=profile['qualification_reason'],
    )
    try:
      params = _params()
      error = params.get('C3XLQnnWifiLastError')
      output['auth_error'] = error == 'authentication_failed'
    except Exception:
      pass
  except Exception:
    output['qualification_reason'] = '配置或资格记录不可用，请重新核对'
  return output


def probe_ready(path=PROFILE):
  """Only a completed OPIF session proves startup availability."""
  profile=load_profile(path,require_enabled=True)
  if profile.get('wire_protocol')!='opif_tcp':
    raise QnnError('Automatic phone startup needs the reviewed OPIF TCP profile')
  from .probe_lock import exclusive_probe
  with exclusive_probe():
    link=None
    try:
      link=connect_qnn(profile,'diagnostic')
      health=link.hello(timeout=5)
      if health.get('ready') is not True or health.get('model_sha256')!=CINQUE_SHA:
        raise QnnError('Phone is not ready with the expected Cinque ABI')
    finally:
      if link is not None:link.close()


def mark_failed(params=None, reason=''):
  params = _params(params)
  params.put_bool('C3XLQnnWifiFailedThisOnroad', True, block=True)
  params.put_bool('C3XLQnnWifiControl', False, block=True)
  auth = any(word in str(reason).lower() for word in ('auth', 'certificate', 'fingerprint', 'unpaired', 'revoked', 'pairing'))
  params.put('C3XLQnnWifiLastError', 'authentication_failed' if auth else 'remote_session_failed')


def discover(timeout=3):
  """mDNS records are untrusted candidates; never auto-pair their advertised pin."""
  try:
    result = subprocess.run(['avahi-browse', '-rtp', '_qnn-infer._tcp'], capture_output=True, text=True, timeout=timeout, check=False)
    raw = result.stdout
  except subprocess.TimeoutExpired as e:
    raw = e.stdout or b''
    if isinstance(raw, bytes):
      raw = raw.decode('utf-8', 'replace')
  except OSError:
    return {'devices': [], 'discovery_available': False, 'reason': 'avahi-browse unavailable; use the phone IP and shown fingerprint'}
  devices = []
  seen = set()
  for row in raw.splitlines():
    fields = row.split(';')
    if len(fields) < 10 or fields[0] != '=' or fields[2] != 'IPv4':
      continue
    try:
      host = str(ipaddress.IPv4Address(fields[7]))
      port = int(fields[8])
      if not 1 <= port <= 65535 or (host, port) in seen:
        continue
      seen.add((host, port))
      txt = dict(item.split('=', 1) for item in re.findall(r'"([^"\n]*)"', fields[9]) if '=' in item)
      devices.append(
        {
          'name': fields[3][:80],
          'host': host,
          'port': port,
          'device_id': txt.get('device_id', ''),
          'advertised_fingerprint': txt.get('fingerprint_sha256', ''),
          'protocol': txt.get('protocol', ''),
          'soc': txt.get('soc', ''),
          'source_sha256': txt.get('source_sha256', ''),
          'runtime_model_sha256': txt.get('runtime_model_sha256', ''),
          'ready': txt.get('ready', ''),
          'trusted': False,
        }
      )
    except (ValueError, IndexError):
      continue
  return {'devices': devices, 'discovery_available': True}


def _atomic_json(path, value, *, replace=True):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
  temporary = path.with_name(path.name + '.new')
  fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
  try:
    with os.fdopen(fd, 'w') as f:
      json.dump(value, f, indent=2)
      f.write('\n')
      f.flush()
      os.fsync(f.fileno())
    if replace:
      os.replace(temporary, path)
    else:
      os.link(temporary, path)  # Publish only if absent; never overwrite existing trust.
  finally:
    temporary.unlink(missing_ok=True)


def _require_offroad(params, offroad_check=None):
  if not params.get_bool('IsOffroad') or (offroad_check is not None and not offroad_check()):
    raise QnnError('Pairing changes require offroad')


def pair_and_save(host, port, fingerprint, code, *, path=PROFILE, params=None, offroad_check=None,
                  capture_width=1928, capture_height=1208, label='C3XL', execution_mode='npu_only'):
  """Explicitly confirmed pin -> real TLS pair -> private files. Never return credentials."""
  params, path = _params(params), Path(path)
  _require_offroad(params, offroad_check)
  if execution_mode not in EXECUTION_MODES:
    raise QnnError('Unknown execution mode')
  host = str(ipaddress.IPv4Address(host))
  port = int(port)
  if not 1 <= port <= 65535 or not isinstance(fingerprint, str) or not HEX.fullmatch(fingerprint):
    raise QnnError('Invalid endpoint or fingerprint')
  if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
    raise QnnError('Expected six-digit temporary pairing code')
  if (capture_width, capture_height) not in ((1928, 1208), (1344, 760)):
    raise QnnError('Unsupported capture geometry')
  if path.exists() or path.is_symlink():
    raise QnnError('Profile already exists; forget its local pairing before replacement')
  credentials = pair(host, port, fingerprint, code, label)
  _require_offroad(params, offroad_check)
  client_id = credentials.get('client_id', '')
  if not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', client_id) or not HEX.fullmatch(credentials.get('token', '')):
    raise QnnError('Invalid pairing identity')
  if not isinstance(credentials.get('device_id'), str) or not 1 <= len(credentials['device_id']) <= 128:
    raise QnnError('Invalid phone identity')
  credential_file = path.parent / 'pairings' / (client_id + '.json')
  if path.parent.is_symlink() or credential_file.parent.is_symlink():
    raise QnnError('Unsafe pairing directory')
  created = False
  try:
    _atomic_json(credential_file, credentials, replace=False)
    created = True
    _require_offroad(params, offroad_check)
    profile = {'schema': 1, 'transport': 'qnn_wifi', 'host': host, 'port': port,
               'device_id': credentials['device_id'], 'fingerprint_sha256': fingerprint,
               'pairing_file': str(credential_file), 'model_sha256': CINQUE_SHA, 'bundle_ref': BUNDLE_REF,
               'capture_width': capture_width, 'capture_height': capture_height, 'execution_mode': execution_mode, 'allow_control': False,
               'frame_delay_seconds': 0.1, 'maximum_result_age_seconds': 0.2}
    params.put_bool('C3XLQnnWifiControl', False, block=True)
    params.put_bool('C3XLQnnWifiEnabled', False, block=True)
    _require_offroad(params, offroad_check)
    _atomic_json(path, profile, replace=False)
  except Exception:
    if created:
      credential_file.unlink(missing_ok=True)
    raise
  params.remove('C3XLQnnWifiLastError')
  return {'paired': True, 'endpoint': f'{host}:{port}', 'device_id': credentials['device_id'],
          'fingerprint_sha256': fingerprint, 'execution_mode': execution_mode, 'control_qualified': False, 'auth_error': False,
          'qualification_reason': '新配对默认关闭；未授予模型控制资格'}



def configure_opif(host, port=5555, *, path=PROFILE, params=None, offroad_check=None,
                   capture_width=1928, capture_height=1208):
  """One explicit source-ABI profile works with either OPIF TCP App. No inferred trust."""
  params, path = _params(params), Path(path)
  _require_offroad(params, offroad_check)
  host = str(ipaddress.IPv4Address(host))
  port = int(port)
  if not 1 <= port <= 65535 or (capture_width, capture_height) not in ((1928, 1208), (1344, 760)):
    raise QnnError('Invalid OPIF endpoint or capture geometry')
  if path.exists() or path.is_symlink():
    raise QnnError('A phone profile already exists; forget it explicitly before replacement')
  profile = {'schema': 1, 'transport': 'qnn_wifi', 'wire_protocol': 'opif_tcp', 'host': host, 'port': port,
             'device_id': 'unverified-opif-endpoint', 'transport_authenticated': False,
             'model_sha256': CINQUE_SHA, 'bundle_ref': BUNDLE_REF,
             'capture_width': capture_width, 'capture_height': capture_height, 'execution_mode': 'npu_only',
             'allow_control': False, 'frame_delay_seconds': .1, 'maximum_result_age_seconds': .2}
  params.put_bool('C3XLQnnWifiControl', False, block=True)
  params.put_bool('C3XLQnnWifiEnabled', False, block=True)
  _require_offroad(params, offroad_check)
  _atomic_json(path, profile, replace=False)
  return status(path)



def set_control_preference(value, path=PROFILE, *, params=None, offroad_check=None):
  """Save intent in the private profile; every startup still validates authority."""
  params, path = _params(params), Path(path)
  _require_offroad(params, offroad_check)
  if type(value) is not bool:
    raise QnnError('Control preference must be a boolean')
  load_profile(path)  # Reject invalid identity/configuration, not missing qualification.
  profile = _read(path)
  profile['prefer_control'] = value
  profile['allow_control'] = False  # Never persist an effective runtime authorization.
  _require_offroad(params, offroad_check)
  params.put_bool('C3XLQnnWifiControl', False, block=True)
  _require_offroad(params, offroad_check)
  _atomic_json(path, profile)


def set_execution_mode(execution_mode, path=PROFILE, *, params=None, offroad_check=None):
  """Explicit local-profile change only. The operator selects the same phone mode separately."""
  params, path = _params(params), Path(path)
  _require_offroad(params, offroad_check)
  if execution_mode not in EXECUTION_MODES:
    raise QnnError('Unknown execution mode')
  load_profile(path)  # Validate saved identity/credentials before modifying its mode.
  profile = _read(path)
  _require_offroad(params, offroad_check)
  params.put_bool('C3XLQnnWifiControl', False, block=True)
  params.put_bool('C3XLQnnWifiEnabled', False, block=True)
  profile['execution_mode'], profile['allow_control'] = execution_mode, False
  _require_offroad(params, offroad_check)
  _atomic_json(path, profile)
  return status(path)

def forget_pairing(path=PROFILE, *, params=None, offroad_check=None):
  """Forget local trust only. Phone-side revocation is a separate app action."""
  params, path = _params(params), Path(path)
  _require_offroad(params, offroad_check)
  credential = None
  if path.exists() or path.is_symlink():
    profile = _read(path)
    candidate = Path(profile.get('pairing_file', '/__no_opif_pairing__'))
    managed = path.parent / 'pairings'
    if (candidate.parent.resolve() == managed.resolve() and not managed.is_symlink()
        and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\.json', candidate.name)
        and not candidate.is_symlink() and (not candidate.exists() or candidate.is_file())):
      credential = candidate
    elif candidate.exists():
      raise QnnError('Credential is outside the managed pairing directory; refuse deletion')
  _require_offroad(params, offroad_check)
  params.put_bool('C3XLQnnWifiControl', False, block=True)
  params.put_bool('C3XLQnnWifiEnabled', False, block=True)
  _require_offroad(params, offroad_check)
  path.unlink(missing_ok=True)
  if credential is not None:
    credential.unlink(missing_ok=True)
  params.remove('C3XLQnnWifiLastError')
  return {'paired': False, 'local_credentials_removed': credential is not None, 'phone_revoked': False}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  sub = parser.add_subparsers(dest='command', required=True)
  for name in ('status', 'startup', 'selected'):
    sub.add_parser(name).add_argument('--profile', type=Path, default=PROFILE)
  opif = sub.add_parser('configure-opif')
  opif.add_argument('--host', required=True)
  opif.add_argument('--port', type=int, default=5555)
  opif.add_argument('--capture-width', type=int, default=1928)
  opif.add_argument('--capture-height', type=int, default=1208)
  opif.add_argument('--profile', type=Path, default=PROFILE)
  sub.add_parser('discover')
  sub.add_parser('unpair').add_argument('--profile', type=Path, default=PROFILE)
  mode = sub.add_parser('execution-mode')
  mode.add_argument('--mode', choices=EXECUTION_MODES, required=True)
  mode.add_argument('--profile', type=Path, default=PROFILE)
  failure = sub.add_parser('fail')
  failure.add_argument('--reason', default='remote_session_failed')
  pairing = sub.add_parser('pair')
  pairing.add_argument('--host', required=True)
  pairing.add_argument('--port', type=int, default=5600)
  pairing.add_argument('--fingerprint', required=True, help='Full SHA256 explicitly compared with the phone screen')
  pairing.add_argument('--label', default='C3XL')
  pairing.add_argument('--execution-mode', choices=EXECUTION_MODES, default='npu_only')
  pairing.add_argument('--capture-width', type=int, default=1928)
  pairing.add_argument('--capture-height', type=int, default=1208)
  pairing.add_argument('--profile', type=Path, default=PROFILE)
  args = parser.parse_args()
  if args.command == 'configure-opif':
    print(json.dumps(configure_opif(args.host, args.port, path=args.profile, capture_width=args.capture_width, capture_height=args.capture_height), ensure_ascii=False, indent=2))
  elif args.command == 'discover':
    print(json.dumps(discover(), ensure_ascii=False, indent=2))
  elif args.command == 'status':
    print(json.dumps(status(args.profile), ensure_ascii=False, indent=2))
  elif args.command == 'selected':
    try:
      return 0 if _params().get_bool('C3XLQnnWifiEnabled') else 1
    except Exception:
      return 2
  elif args.command == 'startup':
    try:
      probe_ready(args.profile)
    except Exception as error:
      if not _params().get_bool('IsOffroad'):
        mark_failed(reason=str(error))
      return 1
    print(args.profile)
  elif args.command == 'fail':
    mark_failed(reason=args.reason)
  elif args.command == 'execution-mode':
    print(json.dumps(set_execution_mode(args.mode, args.profile), ensure_ascii=False))
  elif args.command == 'unpair':
    print(json.dumps(forget_pairing(args.profile)))
  elif args.command == 'pair':
    params = _params()
    _require_offroad(params)
    code = getpass.getpass('Phone short-lived pairing code: ')
    result = pair_and_save(args.host, args.port, args.fingerprint, code, path=args.profile, params=params,
                           capture_width=args.capture_width, capture_height=args.capture_height, label=args.label, execution_mode=args.execution_mode)
    print(json.dumps(result, ensure_ascii=False))
  return 0


if __name__ == '__main__':
  try:
    sys.exit(main())
  except (QnnError, OSError, ValueError) as error:
    print(f'QNN operation failed: {error}', file=sys.stderr)
    sys.exit(1)
