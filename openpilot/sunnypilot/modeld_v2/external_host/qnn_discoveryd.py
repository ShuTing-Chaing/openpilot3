"""Prefer a bound USB phone, otherwise discover Wi-Fi; update only offroad."""
from functools import wraps
import hashlib
import fcntl
import ipaddress
import json
import os
import re
from pathlib import Path
import subprocess
import time

from .qnn_cli import PROFILE, _atomic_json, _read, discover, load_profile
from .qnn_client import connect_qnn

STATUS=Path('/dev/shm/qnn-discovery-status.json')
LOCK='/dev/shm/qnn-discovery.lock'
SOURCE_SHA='404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4'


def network(interface='wlan0'):
  try:
    result=subprocess.run(['ip','-j','-4','addr','show','dev',interface],capture_output=True,text=True,timeout=2,check=True)
    for interface in json.loads(result.stdout):
      if interface.get('operstate')!='UP':continue
      for address in interface.get('addr_info',[]):
        if address.get('family')=='inet' and address.get('scope')=='global':
          value=ipaddress.ip_interface(f"{address['local']}/{address['prefixlen']}")
          if value.network.num_addresses<=4096:return str(value.network)
  except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
  return None


def publish(**state):
  state['connection_revision']='recovery-probe-v3'
  state['updated_boottime']=time.clock_gettime(time.CLOCK_BOOTTIME)
  temporary=STATUS.with_suffix(f'.{os.getpid()}.tmp')
  try:temporary.write_text(json.dumps(state,ensure_ascii=False)+'\n');temporary.replace(STATUS)
  except OSError:pass


def usb_endpoint(profile):
  """Physical USB binding chooses an endpoint; it is not model authentication."""
  expected=profile.get('usb_device_serial')
  if not isinstance(expected,str) or not expected or len(expected)>128:return None
  try:
    interface=Path('/sys/class/net/usb0/device')
    driver=(interface/'driver').resolve().name
    if driver not in ('rndis_host','cdc_ncm'):return None
    serial=(interface.resolve().parent/'serial').read_text().strip()
    if serial!=expected:return None
    lease=subprocess.run(['nmcli','-f','DHCP4.OPTION','dev','show','usb0'],capture_output=True,text=True,timeout=2,check=True)
    match=re.search(r'\brouters = ([0-9.]+)',lease.stdout)
    if not match:return None
    host=str(ipaddress.IPv4Address(match.group(1)))
    route=subprocess.run(['ip','-j','-4','route','get',host],capture_output=True,text=True,timeout=2,check=True)
    routes=json.loads(route.stdout)
    if len(routes)!=1 or routes[0].get('dev')!='usb0':return None
    return {'host':host,'port':5555,'serial':serial,'driver':driver,'interface':'usb0'}
  except (OSError,ValueError,KeyError,subprocess.SubprocessError):return None


def hotspot_endpoint(profile):
  """Find the sole reachable peer on the dedicated C3XL AP, without a MAC pin."""
  ssid=profile.get('hotspot_ssid')
  if not ssid:return None
  try:
    def command(args):
      return subprocess.run(args,capture_output=True,text=True,timeout=2,check=True).stdout.strip()
    ap_active=subprocess.run(['systemctl','is-active','--quiet','c3xl-hotspot-ap.service'],timeout=2).returncode==0
    interface='p2p0' if ap_active else 'wlan0'
    if not ap_active:
      uuid=command(['nmcli','-g','GENERAL.CON-UUID','device','show','wlan0'])
      if command(['nmcli','-g','802-11-wireless.mode','connection','show','uuid',uuid])!='ap':return None
      if command(['nmcli','-g','802-11-wireless.ssid','connection','show','uuid',uuid])!=ssid:return None
    subnet=ipaddress.ip_network(network(interface))
    neighbors=json.loads(command(['ip','-j','-4','neigh','show','dev',interface]))
    hosts={str(ipaddress.IPv4Address(row['dst'])) for row in neighbors
           if not set(row.get('state',[]))&{'FAILED','INCOMPLETE'}
           and ipaddress.ip_address(row['dst']) in subnet}
    if not 1<=len(hosts)<=8:return None
    reachable=[]
    for host in sorted(hosts):
      try:
        if subprocess.run(['ping','-n','-I',interface,'-c','1','-W','1',host],
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=.6).returncode==0:
          reachable.append(host)
      except (OSError,subprocess.TimeoutExpired):pass
    if len(reachable)==1:return {'host':reachable[0],'port':5555,'interface':interface}
  except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):pass
  return None


def offroad_probe(function):
  @wraps(function)
  def wrapped(endpoint,params,profile_path=PROFILE):
    from .probe_lock import exclusive_probe
    try:
      with exclusive_probe(timeout=0.):
        if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):
          return {'phase':'onroad_probe_suppressed'}
        if subprocess.run(['pgrep','-x','camerad'],stdout=subprocess.DEVNULL).returncode!=1:
          return {'phase':'camera_probe_suppressed'}
        return function(endpoint,params,profile_path)
    except TimeoutError:
      return {'phase':'startup_probe_busy'}
  return wrapped


@offroad_probe
def inspect_hotspot_once(endpoint,params,profile_path=PROFILE):
  profile=load_profile(profile_path)
  result={'phase':'observed','transport_link':'wifi_hotspot','host':endpoint['host'],'port':5555}
  if profile.get('wire_protocol')!='opif_tcp':return dict(result,phase='profile_incompatible')
  if hotspot_endpoint(profile)!=endpoint:return dict(result,phase='hotspot_binding_changed')
  link=None
  try:
    link=connect_qnn(dict(profile,host=endpoint['host'],allow_control=False),'diagnostic')
    health=link.hello(timeout=5)
    if health.get('ready') is not True:return dict(result,phase='not_ready')
  except Exception as failure:return dict(result,phase='not_ready',reason=type(failure).__name__)
  finally:
    if link is not None:link.close()
  current=_read(profile_path)
  if hotspot_endpoint(current)!=endpoint:return dict(result,phase='hotspot_binding_changed')
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):return result
  updated=dict(current,host=endpoint['host'])
  if updated!=current:_atomic_json(profile_path,updated)
  return dict(result,phase='endpoint_updated' if updated!=current else 'endpoint_current')


@offroad_probe
def inspect_usb_once(endpoint,params,profile_path=PROFILE):
  result={'phase':'observed','transport_link':'usb','host':endpoint['host'],'port':5555,
          'usb_driver':endpoint['driver'],'usb_device_serial':endpoint['serial'],
          'runtime_identity_verified':False}
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):return result
  profile=load_profile(profile_path)
  # load_profile derives effective control eligibility; the offroad readiness
  # probe below explicitly stays diagnostic even for a qualified preference.
  if profile.get('wire_protocol')!='opif_tcp':
    return dict(result,phase='profile_incompatible')
  if usb_endpoint(profile)!=endpoint:return dict(result,phase='usb_binding_changed')
  link=None
  try:
    link=connect_qnn(dict(profile,host=endpoint['host'],port=5555,allow_control=False),'diagnostic')
    health=link.hello(timeout=5)
    result['runtime_identity_verified']=health.get('runtime_identity_verified') is True
  except Exception as failure:
    return dict(result,phase='not_ready',reason=type(failure).__name__)
  finally:
    if link is not None:link.close()
  current=_read(profile_path)
  if usb_endpoint(current)!=endpoint:return dict(result,phase='usb_binding_changed')
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):return result
  updated=dict(current,host=endpoint['host'])
  if updated!=current:
    _atomic_json(profile_path,updated)
    result.update(phase='endpoint_updated',previous_sha256=hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest())
  else:result['phase']='endpoint_current'
  return result


def candidates(records,subnet):
  addresses=ipaddress.ip_network(subnet)
  return [row for row in records if row.get('protocol')=='opif_tcp' and row.get('port')==5555
          and row.get('ready')=='1' and row.get('source_sha256')==SOURCE_SHA
          and row.get('soc','').upper().startswith('SM8850')
          and ipaddress.ip_address(row['host']) in addresses]


@offroad_probe
def inspect_once(subnet,params,profile_path=PROFILE):
  available=candidates(discover(timeout=3).get('devices',[]),subnet)
  if len(available)!=1:
    return {'phase':'ambiguous' if available else 'not_found','candidate_count':len(available),'subnet':subnet}
  device=available[0]
  profile=load_profile(profile_path)
  if profile.get('wire_protocol')!='opif_tcp':
    return {'phase':'profile_incompatible','subnet':subnet}
  configured_id=profile.get('discovery_device_id')
  if configured_id and configured_id!=device.get('device_id'):
    return {'phase':'device_id_changed','subnet':subnet}
  result={'phase':'observed','subnet':subnet,'host':device['host'],'port':5555,'soc':device['soc'],
          'runtime_model_sha256':device['runtime_model_sha256'],'candidate_count':1}
  # Never acquire a second OPIF session or change the active host during a drive.
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):
    return result
  link=None
  try:
    probe=dict(profile,host=device['host'],port=5555,allow_control=False)
    link=connect_qnn(probe,'diagnostic');link.hello(timeout=5)
  except Exception as failure:
    return dict(result,phase='not_ready',reason=type(failure).__name__)
  finally:
    if link is not None:link.close()
  current=_read(profile_path)
  updated=dict(current,host=device['host'])
  if not current.get('discovery_device_id') and device.get('device_id'):
    updated['discovery_device_id']=device['device_id']
  if updated!=current and params.get_bool('IsOffroad') and not params.get_bool('IsEngaged'):
    _atomic_json(profile_path,updated)
    result['phase']='endpoint_updated'
    result['previous_sha256']=hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()
  else:result['phase']='endpoint_current'
  return result


def main():
  from openpilot.common.params import Params
  descriptor=os.open(LOCK,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  # A manually started offroad watcher may overlap the next manager start.
  # Wait for the owner instead of running two discovery probes in parallel.
  fcntl.flock(descriptor,fcntl.LOCK_EX)
  params=Params();previous=None;next_check=0.;recovery_next=0.;recovery_until=0.;last_usb_seen=0.
  while True:
    subnet=network();now=time.monotonic()
    try:usb=usb_endpoint(_read(PROFILE))
    except (OSError,ValueError):usb=None
    # A USB function reset can leave an authorized phone in MTP/ADB with no
    # tether address. Repair only offroad, at most once per 30 seconds. Keep
    # the existing host while DHCP recovers; never alter a live drive session.
    if usb is None and now>=recovery_next:
      recovery_next=now+1
      try:
        from .usb_recovery import recover
        recovery=recover(_read(PROFILE),params)
        if recovery['phase']=='usb_recovery_requested':
          recovery_next=now+30;recovery_until=now+15;publish(**recovery)
        elif recovery['phase'] in ('usb_recovery_adb_unauthorized','usb_recovery_helper_unverified'):
          recovery_next=now+10;publish(**recovery)
        elif recovery['phase']=='usb_recovery_adb_unavailable':
          publish(**recovery)
      except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        recovery_next=now+10;publish(phase='usb_recovery_failed')
    if usb:
      last_usb_seen=now
      if recovery_until:
        recovery_until=0.;next_check=0.
    if usb is None and (now<recovery_until or (last_usb_seen>0 and now-last_usb_seen<8)):
      time.sleep(1);continue
    hotspot=None
    if usb is None and params.get_bool('IsOffroad') and not params.get_bool('IsEngaged'):
      try:hotspot=hotspot_endpoint(_read(PROFILE))
      except (OSError,ValueError):pass
    signature=(subnet,tuple(sorted(usb.items())) if usb else None,tuple(sorted(hotspot.items())) if hotspot else None)
    if signature!=previous:previous=signature;next_check=0.
    if (usb or subnet) and now>=next_check and params.get_bool('C3XLQnnWifiEnabled'):
      try:
        result=inspect_usb_once(usb,params) if usb else (inspect_hotspot_once(hotspot,params) if hotspot else inspect_once(subnet,params))
        publish(**result)
        next_check=time.monotonic()+(60 if result['phase'] in ('endpoint_current','endpoint_updated') else 10)
      except Exception as failure:
        publish(phase='error',subnet=subnet,reason=type(failure).__name__)
        next_check=time.monotonic()+10
    elif not subnet and not usb:publish(phase='network_disconnected')
    time.sleep(1)


if __name__=='__main__':main()
