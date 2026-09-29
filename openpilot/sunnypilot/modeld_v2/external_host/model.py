"""CTM host adapter selected by the C3XL developer control."""
import base64
import hashlib
import ipaddress
import sys
import json
import subprocess
import threading
import time
from pathlib import Path
import numpy as np
from .wire import HostLink,HostError,MODEL_SHA,tcp,usbmux
from .session import AsyncSession

PINNED_BUNDLE_REF='68b5f8e48602f4f88041efd7de6c99e97fda454e'
SLICES={'lane_lines':(0,528),'lane_lines_prob':(528,536),'road_edges':(536,800),'meta':(800,855),
 'desire_pred':(855,887),'pose':(887,899),'wide_from_device_euler':(899,905),'road_transform':(905,917),
 'plan':(917,1907),'lead':(1907,2051),'lead_prob':(2051,2054),'desire_state':(2054,2062),
 'action':(2062,2066),'hidden_state':(2066,18450),'pad':(18450,18452)}


def mac_wifi_hosts(config):
  """Resolve a paired host on the LAN, then try its last known IPv4 address."""
  hosts=[]
  name=config.get('host_mdns')
  if isinstance(name,str) and name.endswith('.local') and not name.startswith('-'):
    try:
      result=subprocess.run(['/usr/bin/avahi-resolve-host-name','-4',name],capture_output=True,
                            text=True,check=True,timeout=2)
      hosts.append(str(ipaddress.IPv4Address(result.stdout.split()[-1])))
    except (OSError,ValueError,IndexError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
      pass
  if config.get('host'):
    try:hosts.append(str(ipaddress.IPv4Address(config['host'])))
    except ipaddress.AddressValueError:raise HostError('Invalid Mac Wi-Fi host address')
  return list(dict.fromkeys(hosts))


def pairing_key(path, expected_sha256=None):
  key=base64.b64decode(json.loads(Path(path).read_text())['key'],validate=True)
  if len(key)!=32:raise HostError('Invalid host pairing key length')
  if expected_sha256 is not None and hashlib.sha256(key).hexdigest()!=expected_sha256:
    raise HostError('Host pairing identity differs from selected profile')
  return key

def create_model(base_class, config_path, cam_w, cam_h, progress):
  config=json.loads(Path(config_path).read_text())
  from .opt_in import enabled as external_ctm_enabled
  if not external_ctm_enabled():
    raise HostError("External CTM requires the C3XL offroad developer opt-in")
  if config.get("allow_control") is not True:
    raise HostError("External CTM control qualification is incomplete; use the local model")
  from openpilot.sunnypilot.modeld_v2.modeld_base import ModelStateBase
  from openpilot.sunnypilot.models.helpers import get_active_bundle
  from openpilot.sunnypilot.models.split_model_constants import SplitModelConstants
  from openpilot.sunnypilot.modeld_v2.parse_model_outputs import Parser
  from openpilot.selfdrive.modeld.compile_modeld import NV12Frame,make_warp
  from openpilot.system.camerad.cameras.nv12_info import get_nv12_info
  from tinygrad import Tensor,TinyJit
  if config.get('model_sha256')!=MODEL_SHA or config.get('bundle_ref')!=PINNED_BUNDLE_REF:
    raise HostError('External CTM artifact identity differs')
  bundle=get_active_bundle(chestnut=True)
  if bundle is None or bundle.internalName!='CTM' or bundle.ref!=PINNED_BUNDLE_REF or bundle.generation!=12 or not bundle.is20hz:
    raise HostError('Selected CTM bundle does not match the external graph')
  if (cam_w,cam_h)!=(1928,1208):raise HostError('External CTM capture geometry was not qualified')
  delay=float(config['frame_delay_seconds'])
  if not .05<=delay<=.15:raise HostError('Unqualified expected frame delay')
  mode=config['transport']
  key=pairing_key(config['pairing_file']) if mode!='host_auto' else None
  def authenticate(candidate, pairing, timeout=5):
    session=HostLink(candidate,pairing,timeout=.2,client_role="modeld")
    try:session.hello(timeout=timeout)
    except Exception:candidate.close();raise
    return session
  if mode in ('mac_usb','mac_auto','host_auto'):
    sys.path.insert(0,str(Path(__file__).resolve().parent/'vendor'))
    from .bulk_bridge import gadget_socket
  if mode=='mac_auto':
    failures=[];link=None;channel=None;selected_transport='mac_usb'
    try:
      channel=gadget_socket(gadget='/sys/kernel/config/usb_gadget/jetlink',udc='a600000.dwc3')
      link=authenticate(channel,key,timeout=2)
    except Exception as error:failures.append(f'USB: {error}')
    if link is None:
      for host in mac_wifi_hosts(config):
        for attempt in range(2):
          try:
            channel=tcp(host,connect_timeout=1.5)
            link=authenticate(channel,key,timeout=2)
            selected_transport='wifi'
            break
          except Exception as error:
            failures.append(f'Wi-Fi {host} attempt {attempt+1}: {error}')
            time.sleep(.4)
        if link is not None:break
    if link is None:raise HostError('Mac unavailable over USB and Wi-Fi: '+'; '.join(failures))
    selected_host='mac'
  elif mode=='host_auto':
    entries=config.get('hosts')
    if not isinstance(entries,list) or not 1<=len(entries)<=3:
      raise HostError('Host selector requires one to three ordered profiles')
    failures=[];link=None;channel=None;selected_transport=None;selected_host=None;seen=set()
    for entry in entries:
      if not isinstance(entry,dict) or entry.get('name') not in ('mac','iphone'):
        raise HostError('Invalid external host identity')
      transport=entry.get('transport')
      if transport not in ('mac_usb','wifi'):
        raise HostError('Unsupported external host transport')
      profile=(entry['name'],transport)
      if profile in seen:
        raise HostError('Repeated external host profile')
      seen.add(profile)
      if entry['name']=='iphone' and transport!='wifi':
        raise HostError('iPhone host profile must use Wi-Fi')
      host_key=pairing_key(entry['pairing_file'],entry.get('pairing_key_sha256'))
      if not entry.get('pairing_key_sha256'):
        raise HostError('Pinned pairing fingerprint is required for each host')
      if transport=='mac_usb':
        try:
          channel=gadget_socket(gadget='/sys/kernel/config/usb_gadget/jetlink',udc='a600000.dwc3')
          link=authenticate(channel,host_key,timeout=2)
        except Exception as error:failures.append(f"{entry['name']} USB: {error}")
      else:
        addresses=mac_wifi_hosts(entry)
        if not addresses:failures.append(f"{entry['name']} Wi-Fi: no current address")
        for address in addresses:
          for attempt in range(2):
            try:
              channel=tcp(address,connect_timeout=1.5)
              link=authenticate(channel,host_key,timeout=2)
              break
            except Exception as error:
              failures.append(f"{entry['name']} Wi-Fi attempt {attempt+1}: {error}")
              time.sleep(.4)
          if link is not None:break
      if link is not None:
        selected_transport=transport
        selected_host=entry['name']
        break
    if link is None:raise HostError('No paired external host available: '+'; '.join(failures))
  else:
    if mode=='wifi':channel=tcp(config['host'])
    elif mode=='iphone_usb':channel=usbmux(config['udid'])
    elif mode=='mac_usb':channel=gadget_socket(gadget='/sys/kernel/config/usb_gadget/jetlink',udc='a600000.dwc3')
    else:raise HostError('Unknown external transport')
    selected_transport=mode
    selected_host='iphone' if mode=='iphone_usb' else 'mac'
    link=authenticate(channel,key)
  print(f'CTM_HOST_SELECTED {selected_host} {selected_transport}',flush=True)

  class ExternalModel(base_class):
    external_host=True
    def __init__(self):
      ModelStateBase.__init__(self)
      self.chestnut=True;self.generation=12;self.LAT_SMOOTH_SECONDS=.1;self.LONG_SMOOTH_SECONDS=.3
      self.MIN_LAT_CONTROL_SPEED=.3;self.PLANPLUS_CONTROL=1.;self.constants=SplitModelConstants();self.parser=Parser()
      self._vision_input_names=['img','big_img'];self._desire_key='desire'
      self.numpy_inputs={'desire':np.zeros(8,np.float32),'traffic_convention':np.zeros(2,np.float32),'action_t':np.zeros(2,np.float32)}
      self.expected_frame_delay=delay;self.submit_context=None;self.output_context=None;self.output_execution_time=0.
      self.owner_thread=None
      stride,yh,uvh,size=get_nv12_info(cam_w,cam_h);self.frame_size=size
      base=make_warp(NV12Frame(cam_w,cam_h,stride,yh,uvh,size),512,256)
      self.warp=TinyJit(lambda tfm,big_tfm,frame,big_frame:base(tfm,big_tfm,frame,big_frame).realize())
      self.blobs={}
      dummy=[Tensor(np.zeros(size,np.uint8),device='QCOM').realize() for _ in range(2)]
      tfms=[Tensor(np.eye(3,dtype=np.float32),device='NPY').realize() for _ in range(2)]
      for _ in range(3):self.warp(*tfms,*dummy).numpy()
      self.async_session=AsyncSession(link,float(config.get('maximum_result_age_seconds',.2)),warming_up=True)
      self.warm_good_frames=0;self.warm_deadline=None
      self.warmup_budget=2 if selected_transport=='wifi' else 10
      self.host_name=selected_host
      if progress:progress(95)

    def run(self,bufs,transforms,inputs,after_enqueue=None):
      # Model loading may happen on a worker. Bind warp construction/use to the
      # first actual modeld caller, and reject subsequent cross-thread calls.
      tid=threading.get_ident()
      if self.owner_thread is None:self.owner_thread=tid
      if tid!=self.owner_thread:raise HostError('External camera preprocessing changed threads')
      if self.warm_deadline is None:self.warm_deadline=time.monotonic()+self.warmup_budget
      if self.async_session.warming_up and time.monotonic()>self.warm_deadline:
        self.async_session.close();raise HostError('External model did not reach timely output within startup budget')
      context=self.submit_context
      if context is None:raise HostError('Missing matching camera publication context')
      try:
        capture_age=(time.clock_gettime_ns(time.CLOCK_BOOTTIME)-context['meta_main'].timestamp_eof)/1e9
        if not 0<=capture_age<self.async_session.maximum_age:raise HostError('Camera frame is too old')
        completed=self.async_session.poll_latest()
        buffers=[]
        for name in self._vision_input_names:
          data=np.frombuffer(bufs[name].data,dtype=np.uint8)
          if data.size<self.frame_size:raise HostError('Truncated VisionIPC frame')
          key=(name,data.ctypes.data)
          if key not in self.blobs:self.blobs[key]=Tensor.from_blob(data.ctypes.data,(self.frame_size,),dtype='uint8',device='QCOM')
          buffers.append(self.blobs[key])
        tfms=[Tensor(np.ascontiguousarray(transforms[k],dtype=np.float32),device='NPY').realize() for k in self._vision_input_names]
        pixels=np.ascontiguousarray(self.warp(*tfms,*buffers).numpy(),dtype=np.uint8)
        if pixels.shape!=(2,6,128,256):raise HostError('Warped shape differs')
        scalars=np.concatenate([np.asarray(inputs['desire'],np.float32).reshape(8),np.asarray(inputs['traffic_convention'],np.float32).reshape(2),np.asarray(inputs['action_t'],np.float32).reshape(2)]).astype('<f4')
        if not np.isfinite(scalars).all():raise HostError('Nonfinite live control inputs')
        main=context['meta_main']
        if (time.clock_gettime_ns(time.CLOCK_BOOTTIME)-main.timestamp_eof)/1e9>=self.async_session.maximum_age:
          if self.async_session.warming_up:return None
          raise HostError('Camera preprocessing exceeded the result deadline')
        if completed is None:
          completed=self.async_session.poll_latest(timeout=.2 if len(self.async_session.pending)>=3 else 0)
        if len(self.async_session.pending)>=3 and self.async_session.warming_up:
          # The first CoreML request can take longer after an idle host. Do not
          # fail the session just because its bounded startup queue is full;
          # the 10-second warmup budget and result-age checks still apply.
          self.output_context=None
          return None
        self.async_session.submit(main.frame_id,main.timestamp_eof,pixels.tobytes(),scalars.tobytes(),context)
        if after_enqueue:after_enqueue()
        newest=self.async_session.poll_latest(timeout=.03 if completed is None else 0)
        if newest is not None:
          if completed is not None:self.async_session.superseded_outputs+=1
          completed=newest
        if completed is None:self.output_context=None;return None
        output,self.output_context,self.output_execution_time,stats=completed
        age=(time.clock_gettime_ns(time.CLOCK_BOOTTIME)-self.output_context['meta_main'].timestamp_eof)/1e9
        if not 0<=age<self.async_session.maximum_age:
          if self.async_session.warming_up:self.warm_good_frames=0;return None
          raise HostError(f'Capture-to-publication deadline exceeded: {age*1000:.2f} ms, output frame {self.output_context["meta_main"].frame_id}, input frame {main.frame_id}')
        if self.async_session.warming_up:
          self.warm_good_frames+=1
          if self.warm_good_frames<10:return None
          self.async_session.warming_up=False
        raw=np.frombuffer(output,dtype='<f4').copy()
        if raw.size!=18452 or not np.isfinite(raw).all():raise HostError('Invalid external result')
        return self.parser.parse_outputs({k:raw[np.newaxis,slice(*bounds)] for k,bounds in SLICES.items()})
      except Exception:
        self.async_session.close();raise
  try:return ExternalModel()
  except Exception:channel.close();raise
