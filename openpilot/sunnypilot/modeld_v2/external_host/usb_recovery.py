"""Offroad-only repair of a bound, ADB-authorized phone's USB tether service."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HELPER=Path('/data/qnn-host/android-tools/usb-tether.jar')
HELPER_SHA='86342d62317e3e6a956e1583b039a532036985187d1733577e6e902df5300259'


def recover(profile, params):
  if os.environ.get('OPENPILOT_PREFIX') or not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):
    return {'phase':'usb_recovery_suppressed'}
  if not params.get_bool('C3XLQnnWifiEnabled'):
    return {'phase':'usb_recovery_disabled'}
  serial=profile.get('usb_device_serial','')
  if not isinstance(serial,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',serial):
    return {'phase':'usb_recovery_unbound'}
  found=False
  for file in Path('/sys/bus/usb/devices').glob('*/serial'):
    try:
      if file.read_text().strip()==serial:found=True;break
    except OSError:pass
  if not found:return {'phase':'usb_recovery_phone_absent'}
  if subprocess.run(['pgrep','-x','camerad'],stdout=subprocess.DEVNULL).returncode==0:
    return {'phase':'usb_recovery_camera_active'}
  state=subprocess.run(['ip','-j','-4','addr','show','dev','usb0'],capture_output=True,text=True,timeout=2)
  if state.returncode==0 and any(x.get('family')=='inet' for interface in json.loads(state.stdout) for x in interface.get('addr_info',[])):
    return {'phase':'usb_recovery_already_addressed'}
  if not HELPER.is_file() or HELPER.is_symlink() or hashlib.sha256(HELPER.read_bytes()).hexdigest()!=HELPER_SHA:
    return {'phase':'usb_recovery_helper_unverified'}
  adb=['adb','-s',serial]
  authorized=subprocess.run(adb+['get-state'],capture_output=True,text=True,timeout=3)
  if authorized.returncode or authorized.stdout.strip()!='device':
    reason='unauthorized' if 'unauthorized' in (authorized.stdout+authorized.stderr).lower() else 'temporarily_unavailable'
    return {'phase':'usb_recovery_adb_unauthorized' if reason=='unauthorized' else 'usb_recovery_adb_unavailable','adb_state':reason}
  # Recheck the real state immediately before any device mutation.
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged') or subprocess.run(['pgrep','-x','camerad'],stdout=subprocess.DEVNULL).returncode==0:
    return {'phase':'usb_recovery_suppressed'}
  subprocess.run(adb+['push',str(HELPER),'/data/local/tmp/usb-tether.jar'],capture_output=True,check=True,timeout=5)
  actual=subprocess.run(adb+['shell','sha256sum','/data/local/tmp/usb-tether.jar'],capture_output=True,text=True,check=True,timeout=3).stdout.split()[0]
  if actual!=HELPER_SHA:raise RuntimeError('Phone recovery helper transfer differs')
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):
    return {'phase':'usb_recovery_suppressed'}
  command="nohup sh -c 'CLASSPATH=/data/local/tmp/usb-tether.jar app_process / UsbTether start-usb' >/data/local/tmp/usb-restore.log 2>&1 </dev/null &"
  subprocess.run(adb+['shell',command],capture_output=True,check=True,timeout=5)
  return {'phase':'usb_recovery_requested','usb_device_serial':serial}
