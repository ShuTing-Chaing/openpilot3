"""Actuator-disconnected control bench. Encoded CAN goes to a file, never sendcan."""
import argparse,json,os,signal,subprocess,sys,time,shutil,uuid,math,hashlib,re
from pathlib import Path
ROOT=Path('/data/openpilot');PYTHON='/usr/local/venv/bin/python'
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ.setdefault(key,'1')
os.environ.setdefault('QCOM_PRIORITY','12')

def write(path,value):
 path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,default=str)+'\n');os.replace(tmp,path)

def physical_guard():
 from openpilot.common.params import Params
 from openpilot.cereal import messaging
 if os.environ.get('OPENPILOT_PREFIX'):raise RuntimeError('Physical guard must use real namespace')
 params=Params();sm=messaging.SubMaster(['pandaStates','deviceState']);deadline=time.monotonic()+6
 def check():
  sm.update(0)
  if not params.get_bool('IsOffroad') or params.get_bool('IsEngaged'):raise RuntimeError('Real offroad/engagement guard changed')
  if not all(sm.alive[k] and sm.valid[k] for k in ['pandaStates','deviceState']) or not len(sm['pandaStates']):raise RuntimeError('Fresh physical guard unavailable')
  states=[x.to_dict() for x in sm['pandaStates']]
  if any(any(x.get(k) for k in ['ignitionLine','ignitionCan','controlsAllowed','controlsAllowedLateral','controlsAllowedLongitudinal']) or x.get('safetyModel')!='noOutput' or x.get('harnessStatus')!='notConnected' for x in states):raise RuntimeError('Real vehicle/harness/safety state changed')
  ds=sm['deviceState'].to_dict()
  if ds.get('started'):raise RuntimeError('Real device entered onroad')
  return {'deviceState':ds,'pandaStates':states,'offroad':True,'engaged':False,'timestamp_ns':time.monotonic_ns()}
 while time.monotonic()<deadline:
  try:check();return check
  except RuntimeError:time.sleep(.1)
 check();return check

class OperationalStop(RuntimeError):
 def __init__(self,reason,physical):
  super().__init__(reason);self.physical=physical

def guard():
 check_physical=physical_guard()
 def check():
  physical=check_physical();ds=physical['deviceState']
  if ds.get('maxTempC',0)>=75:raise OperationalStop('C3XL temperature reached75C',physical)
  if ds.get('freeSpacePercent',100)<10:raise OperationalStop('Free space below10percent',physical)
  return physical
 check();return check

def restore_hardware(cpu,irq,wifi_tool,wifi_before):
 """Operational limits stop work; only fresh physical ownership gates cleanup."""
 restored={};operations=[]
 try:check_physical=physical_guard()
 except Exception as error:return {'complete':False,'deferred_for_safety':str(error),'operations':operations}
 order=list(irq.items())+[(p,v) for p,v in cpu.items() if not p.endswith('/online')]+[(p,v) for p,v in cpu.items() if p.endswith('/online')]
 for path,value in order:
  try:check_physical()
  except Exception as error:
   restored['deferred_for_safety']=str(error);break
  operation={'path':path,'expected':value}
  try:
   operation['before']=Path(path).read_text().strip()
   if operation['before']!=value:
    result=subprocess.run(['sudo','-n','tee',path],input=value+'\n',text=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=3)
    operation.update(returncode=result.returncode,stderr=result.stderr)
   operation['readback']=Path(path).read_text().strip();restored[path]=operation['readback']==value
  except Exception as error:operation['error']=str(error);restored[path]=False
  operations.append(operation)
 if 'deferred_for_safety' not in restored:
  try:
   check_physical()
   result=subprocess.run(['sudo','-n',str(wifi_tool),'wlan0',wifi_before],text=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=3)
   actual=subprocess.check_output([str(wifi_tool),'wlan0'],text=True,timeout=3).strip()
   restored['wifi_runtime']=result.returncode==0 and actual==wifi_before
   operations.append({'path':'wlan0 power save','expected':wifi_before,'readback':actual,'returncode':result.returncode,'stderr':result.stderr})
   restored['physical_after']=check_physical()
  except Exception as error:restored['wifi_runtime']=False;restored['wifi_restore_error']=str(error)
 restored['complete']=all(restored.get(p) is True for p in dict(cpu,**irq)) and restored.get('wifi_runtime') is True
 restored['operations']=operations
 return restored

def cleanup_namespace(prefix):
 private=Path('/data/params')/prefix
 if not prefix.startswith('qnnbench_') or '/' in prefix:raise RuntimeError('Invalid private cleanup prefix')
 if private.is_symlink():
  target=private.resolve()
  if target.parent!=Path('/data/params') or not target.name.startswith('.tmp'):raise RuntimeError('Unexpected private Params target')
  shutil.rmtree(target);private.unlink()
 shutil.rmtree('/dev/shm/msgq_'+prefix,ignore_errors=True)
 return {'params_removed':not os.path.lexists(private),'messages_removed':not Path('/dev/shm/msgq_'+prefix).exists()}

class CoolingLease:
 def __init__(self):
  self.path=Path('/dev/shm/c3xl-bench-cooling.json');self.token=uuid.uuid4().hex;self.owned=False
  stat=Path(f'/proc/{os.getpid()}/stat').read_text()
  self.value={'schema':1,'token':self.token,'pid':os.getpid(),'pid_start_ticks':int(stat[stat.rfind(')')+2:].split()[19]),
              'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'percent':80}
 def refresh(self):
  if os.path.lexists(self.path):
   if self.path.is_symlink() or not self.owned or json.loads(self.path.read_text()).get('token')!=self.token:raise RuntimeError('Another cooling lease exists')
  self.owned=True
  write(self.path,dict(self.value,expires_boottime=time.clock_gettime(time.CLOCK_BOOTTIME)+2))
 def close(self):
  if self.owned and self.path.exists() and not self.path.is_symlink() and json.loads(self.path.read_text()).get('token')==self.token:self.path.unlink()
  return not os.path.lexists(self.path)

def require_private():
 prefix=os.environ.get('OPENPILOT_PREFIX','')
 if not prefix.startswith('qnnbench_'):raise RuntimeError('Private bench namespace required')
 from openpilot.common.params import Params
 p=Params()
 if p.get_param_path()=='/data/params/d':raise RuntimeError('Params isolation failed')
 return p

def prepare(a):
 from openpilot.common.params import Params
 from openpilot.cereal import messaging
 from opendbc.car.structs import car
 p=require_private();target=Path(p.get_param_path());source=Path('/data/params/d')
 for src in source.iterdir():
  if src.is_file() and not any(x in src.name.lower() for x in ['token','secret','key','github','sunnylink','athena','dongle','carvin']):shutil.copy2(src,target/src.name)
 cp=messaging.log_from_bytes((source/'CarParamsPersistent').read_bytes(),car.CarParams).as_builder()
 cp.safetyConfigs=[{'safetyModel':'noOutput','safetyParam':0}]
 cp.alternativeExperience=0
 cp.passive=False
 p.put('CarParams',cp.to_bytes(),block=True);p.put('CarParamsSP',(source/'CarParamsSPPersistent').read_bytes(),block=True)
 for key,val in {'IsOffroad':False,'IsEngaged':False,'OpenpilotEnabledToggle':True,'C3XLQnnWifiEnabled':True,'C3XLQnnWifiControl':False,'C3XLQnnWifiFailedThisOnroad':False,'C3XLExternalCTMAuto':False,'C3XLExternalCTMControl':False}.items():p.put_bool(key,val,block=True)
 p.remove('C3XLQnnWifiLastError')
 write(a.run/'isolation.json',{'prefix':os.environ['OPENPILOT_PREFIX'],'params_path':str(target),'original_params_path':str(source),'car_params_brand':cp.brand,'private_safety_configs':['noOutput'],'road_control_qualified':False})


def relay(a):
 physical=json.loads((a.run/'physical.json').read_text())
 if time.monotonic_ns()-physical['timestamp_ns']>2_000_000_000:raise RuntimeError('Physical guard relay stale')
 if not physical['offroad'] or physical['engaged']:raise RuntimeError('Physical relay is not offroad')
 if any(x['safetyModel']!='noOutput' or x['harnessStatus']!='notConnected' or x['ignitionLine'] or x['ignitionCan'] or x['controlsAllowed'] for x in physical['pandaStates']):raise RuntimeError('Physical relay unsafe')
 return physical

def feed(a):
 p=require_private()
 from openpilot.cereal import messaging,log
 from opendbc.car.structs import car
 cp=messaging.log_from_bytes(p.get('CarParams'),car.CarParams)
 calibration=messaging.log_from_bytes(p.get('CalibrationParams'),log.Event).extrinsicsCalibration.to_dict()
 services=['deviceState','pandaStates','peripheralState','deviceMotion','carState','carStateSP','carParams','extrinsicsCalibration','radarState','driverMonitoringState','vehicleParameters','lateralDelay','lateralTorqueParameters','accelerometer','gyroscope']
 pm=messaging.PubMaster(services);counter=0;next_tick=time.monotonic();started_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME)
 sm=messaging.SubMaster(['modelV2','longitudinalPlan','selfdriveState','controlsState','carOutput'])
 cruise=False;last_attempt=0.;enabled_since=None
 def send(name,value=None,count=None):
  msg=messaging.new_message(name,count,valid=True) if count is not None else messaging.new_message(name,valid=True)
  if value is not None:setattr(msg,name,value)
  pm.send(name,msg)
 while True:
  physical=relay(a);sm.update(0);now=time.monotonic()
  ready=sm.all_checks(['modelV2','longitudinalPlan','controlsState','carOutput'])
  if ready and sm['selfdriveState'].enabled:
   cruise=True
   if enabled_since is None:enabled_since=now
  elif ready and now-last_attempt>4:
   cruise=False if cruise else True;last_attempt=now
  elif not ready:cruise=False
  elapsed=0 if enabled_since is None else now-enabled_since
  target_kph=80. if int(elapsed//10)%2==0 else 25.
  angle=float(sm['carOutput'].actuatorsOutput.steeringAngleDeg) if sm.valid['carOutput'] else 0.
  send('carState',{'vEgo':12.,'vEgoRaw':12.,'aEgo':0.,'standstill':False,'gearShifter':'drive','canValid':True,
       'vCruise':target_kph,'vCruiseCluster':target_kph,'cruiseState':{'available':True,'enabled':cruise,'speed':target_kph/3.6,'speedCluster':target_kph/3.6},
       'steeringAngleDeg':angle})
  send('carStateSP')
  # These are explicit simulation inputs in the private namespace. Production
  # selfdrived also checks IMU packet age outside SubMaster's ignored services.
  sensor_stamp=time.clock_gettime_ns(time.CLOCK_BOOTTIME)
  send('accelerometer',{'timestamp':sensor_stamp,'acceleration':{'v':[0.,0.,9.81]}})
  send('gyroscope',{'timestamp':sensor_stamp,'gyroUncalibrated':{'v':[0.,0.,0.]}})
  if counter%5==0:
   send('radarState');send('vehicleParameters',{'valid':True,'steerRatio':cp.steerRatio,'stiffnessFactor':1.,'roll':0.})
   send('lateralDelay',{'lateralDelay':.15});send('lateralTorqueParameters');send('driverMonitoringState')
   measurement={'x':0.,'y':0.,'z':0.,'xStd':.01,'yStd':.01,'zStd':.01,'valid':True}
   send('deviceMotion',{'inputsOK':True,'posenetOK':True,'sensorsOK':True,'orientationNED':measurement,'velocityDevice':dict(measurement,x=12.),'accelerationDevice':measurement,'angularVelocityDevice':measurement})
  if counter%10==0:send('pandaStates',physical['pandaStates'],len(physical['pandaStates']))
  if counter%25==0:
   ds=dict(physical['deviceState']);ds['started']=True;ds['startedMonoTime']=started_ns;send('deviceState',ds)
   # Only private deviceState is onroad. Real ignition/noOutput fields are retained.
   send('peripheralState',{'pandaType':'tres','voltage':12000,'current':0})
   send('extrinsicsCalibration',calibration);send('carParams',cp.to_dict())
   write(a.run/'simulated-vehicle.json',{'speed_mps':12.,'cruise_kph':target_kph,'cruise_enabled':cruise,'production_selfdrive_enabled':bool(sm['selfdriveState'].enabled),'inputs_ready':ready})
  counter+=1;next_tick+=.01;time.sleep(max(0,next_tick-time.monotonic()))

def actuator_sink(a):
 p=require_private()
 from openpilot.cereal import messaging,custom
 from opendbc.car.structs import car
 from opendbc.car.car_helpers import interfaces
 cp=messaging.log_from_bytes(p.get('CarParams'),car.CarParams)
 cp_sp=messaging.log_from_bytes(p.get('CarParamsSP'),custom.CarParamsSP)
 if cp.brand!='tesla' or any(str(x.safetyModel)!='noOutput' for x in cp.safetyConfigs):raise RuntimeError('Unexpected isolated vehicle profile')
 ci=interfaces[cp.carFingerprint](cp,cp_sp)
 sm=messaging.SubMaster(['carState','carStateSP','carControl','carControlSP','controlsState','modelV2'])
 # No sendcan publisher exists in this process. This publisher is private feedback only.
 pm=messaging.PubMaster(['carOutput'])
 model_frames={};count=remote_active=lat_active=long_active=can_count=0;minimum_accel=maximum_accel=0.;last_report=0.;next_tick=time.monotonic()
 with (a.run/'actuator-commands.jsonl').open('w',buffering=1) as f:
  while True:
   relay(a);sm.update(0);now=time.monotonic()
   if sm.updated['modelV2']:
    model_frames[sm.logMonoTime['modelV2']]={'frame':int(sm['modelV2'].frameId),'phone':bool(sm['modelV2'].big)}
    while len(model_frames)>4096:del model_frames[next(iter(model_frames))]
   if sm.updated['carControl'] and sm.valid['carState']:
    cc=sm['carControl'];cs=sm['carState'];ci.CS.out=cs
    ci.CS.das_control={'DAS_controlCounter':count%8}
    ci.CS.tesla_stock_longitudinal_active=False;ci.CS.tesla_stock_lateral_active=False;ci.CS.cruise_override=False
    requested=cc.actuators.to_dict()
    if any(not math.isfinite(v) for v in requested.values() if type(v) in (int,float)):raise RuntimeError('Nonfinite actual carControl')
    applied,messages=ci.apply(cc,sm['carControlSP'],time.clock_gettime_ns(time.CLOCK_BOOTTIME))
    encoded=[]
    for item in messages:
     address,data,bus=item;encoded.append({'address':int(address),'bus':int(bus),'data_hex':bytes(data).hex()})
    output=messaging.new_message('carOutput',valid=True);output.carOutput.actuatorsOutput=applied;pm.send('carOutput',output)
    lineage=model_frames.get(int(sm['controlsState'].lateralPlanMonoTime),{})
    active=bool(cc.enabled and cc.latActive and cc.longActive and sm.valid['carControl'])
    count+=1;lat_active+=int(cc.latActive);long_active+=int(cc.longActive);can_count+=len(encoded)
    remote_active+=int(active and lineage.get('phone') is True)
    minimum_accel=min(minimum_accel,float(cc.actuators.accel));maximum_accel=max(maximum_accel,float(cc.actuators.accel))
    f.write(json.dumps({'at':now,'car_control_time':int(sm.logMonoTime['carControl']),'model_time':int(sm['controlsState'].lateralPlanMonoTime),'lineage':lineage,
      'valid':bool(sm.valid['carControl']),'enabled':bool(cc.enabled),'lat_active':bool(cc.latActive),'long_active':bool(cc.longActive),
      'requested':requested,'controller_return':applied.to_dict(),'encoded_can':encoded,'sink':'file_only','real_can_publications':0})+'\n')
   elif not count:
    output=messaging.new_message('carOutput',valid=True);pm.send('carOutput',output)
   if now-last_report>=1:
    write(a.run/'actuator-progress.json',{'commands':count,'phone_active_commands':remote_active,'lat_active_commands':lat_active,'long_active_commands':long_active,'encoded_can_messages':can_count,'accel_min':minimum_accel,'accel_max':maximum_accel,'real_can_publications':0});last_report=now
   next_tick+=.01;time.sleep(max(0,next_tick-time.monotonic()))

def observe(a):
 require_private()
 from openpilot.cereal import messaging
 sm=messaging.SubMaster(['modelV2','drivingModelData','carControl','controlsState','longitudinalPlan','selfdriveState','onroadEvents'],poll='modelV2')
 counts={k:0 for k in sm.alive};valid={k:0 for k in sm.alive};first=None;last=None;gaps=0;max_age=0.;big=0;last_report=0
 with (a.run/'frames.jsonl').open('w',buffering=1) as f:
  while True:
   sm.update(1000);now=time.monotonic()
   for k in counts:
    if sm.updated[k]:counts[k]+=1;valid[k]+=int(sm.valid[k])
   if sm.updated['onroadEvents']:
    with (a.run/'control-events.jsonl').open('a') as events:
     state=sm['selfdriveState']
     # Record the fields under investigation; deprecated enum slots can contain
     # unknown values and must not crash an otherwise valid E2E observer.
     snapshot={'enabled':bool(state.enabled),'active':bool(state.active),'engageable':bool(state.engageable),
               'alertText1':str(state.alertText1),'alertText2':str(state.alertText2),'alertType':str(state.alertType)}
     runtime=json.loads((a.run/'runtime.json').read_text()) if (a.run/'runtime.json').exists() else {}
     events.write(json.dumps({'at':now,'events':[event.to_dict() for event in sm['onroadEvents']],'selfdrive':snapshot,'runtime_phase':runtime.get('phase'),'runtime_source':runtime.get('source')})+'\n')
   if sm.updated['modelV2']:
    m=sm['modelV2'];stamp=time.clock_gettime_ns(time.CLOCK_BOOTTIME);age=(stamp-m.timestampEof)/1e6
    fid=int(m.frameId);gap=max(0,fid-last-1) if last is not None else 0;last=fid;gaps+=gap;max_age=max(max_age,age);big+=int(m.big)
    if first is None:first=now
    f.write(json.dumps({'frame_id':fid,'timestamp_eof':int(m.timestampEof),'received_ns':stamp,'age_ms':age,'big':bool(m.big),'valid':bool(sm.valid['modelV2']),'model_execution_ms':float(m.modelExecutionTime)*1000,'dropped_camera_ids':gap})+'\n')
   if now-last_report>=1:
    write(a.run/'progress.json',{'counts':counts,'valid_counts':valid,'first_frame_monotonic':first,'measured_seconds':now-first if first else 0,'big_frames':big,'camera_id_gaps':gaps,'max_age_ms':max_age,'last_frame':last,'updated_monotonic':now,'control_qualified':False})
    last_report=now

def planner(a):
 require_private()
 from openpilot.cereal import messaging
 original=messaging.SubMaster.all_checks
 previous=None
 def observed(sm,*args,**kwargs):
  nonlocal previous
  result=original(sm,*args,**kwargs)
  state={'valid':result,'invalid':[s for s,v in sm.valid.items() if not v and s not in sm.ignore_valid],
         'not_alive':[s for s,v in sm.alive.items() if not v and s not in sm.ignore_alive],
         'not_freq_ok':[s for s,v in sm.freq_ok.items() if not v and s not in sm.ignore_average_freq]}
  if state!=previous:
   with (a.run/'planner-input-checks.jsonl').open('a') as output:output.write(json.dumps(dict(state,at=time.monotonic(),scope='isolated-bench-observation'))+'\n')
   previous=state
  return result
 messaging.SubMaster.all_checks=observed
 from openpilot.selfdrive.controls.plannerd import main
 main()

def supervise(a):
 if os.environ.get('OPENPILOT_PREFIX'):raise RuntimeError('Supervisor must remain in real namespace')
 wifi_tool=Path('/data/qnn-host/recovery-20260926/build/wifi_power')
 if not wifi_tool.is_file() or not os.access(wifi_tool,os.X_OK):raise RuntimeError('Verified Wi-Fi power helper is unavailable')
 if a.run.exists():raise RuntimeError('Run directory already exists')
 a.run.mkdir(parents=True);check=guard();physical=check();write(a.run/'physical.json',physical)
 prefix='qnnbench_'+uuid.uuid4().hex[:10];Path('/dev/shm/msgq_'+prefix).mkdir()
 env=os.environ.copy();env.update(OPENPILOT_PREFIX=prefix,PYTHONPATH=str(a.run/'observation')+':/data/openpilot',CTM_EXTERNAL_CONFIG=str(a.run/'profile.json'),CTM_COMPARE_TAP_DISABLED='1',XDG_CACHE_HOME=str(a.run/'cache'),LOG_ROOT=str(a.run/'logs'),SUNNYPILOT_HARDWARE_PROFILE='c3xl',DISABLE_DRIVER='1')
 env.pop('C3XL_IFE_ROAD_SIZE',None);env.pop('C3XL_QNN_LOCAL_ONLY',None)
 write(a.run/'profile.json',{'transport':'qnn_wifi','wire_protocol':'opif_tcp','host':a.phone,'port':5555,'device_id':'unverified-opif-endpoint','transport_authenticated':False,'model_sha256':'404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4','bundle_ref':'c6d13eb723e0f6eee47ea7d56e47a700fba21380','capture_width':1928,'capture_height':1208,'execution_mode':'npu_only','allow_control':False,'frame_delay_seconds':.1,'maximum_result_age_seconds':.2})
 if a.usb:
  from openpilot.common.params import Params
  if Params().get_bool('C3XLQnnWifiControl'):raise RuntimeError('Real control request must remain off')
  profile=json.loads(Path('/data/qnn-host/active-host.json').read_text())
  if profile.get('wire_protocol')!='opif_tcp' or profile.get('allow_control') is not False or (profile.get('capture_width'),profile.get('capture_height'))!=(1344,760):raise RuntimeError('USB bench requires reviewed 1344x760 OPIF profile')
  options=subprocess.check_output(['nmcli','-f','DHCP4.OPTION','dev','show','usb0'],text=True)
  router=re.search(r'\brouters = ([0-9.]+)',options)
  if not router or router.group(1)!=a.phone or 'dev usb0' not in subprocess.check_output(['ip','-4','route','get',a.phone],text=True):raise RuntimeError('Phone is not routed through USB DHCP link')
  if Path('/sys/class/net/usb0/device/driver').resolve().name not in ('rndis_host','cdc_ncm'):raise RuntimeError('USB network driver differs')
  env.update(C3XL_IFE_ROAD_SIZE='1344x760',C3XL_IFE_LOCAL_MODEL='/data/ctm-host-apps/models/c3xl-local-1344/driving_tinygrad.pkl')
  profile['host']=a.phone
  write(a.run/'profile.json',profile)
 obs=a.run/'observation';obs.mkdir()
 (obs/'sitecustomize.py').write_text((Path(__file__).parent/'startup_observation.py').read_text())
 env['NORMAL_STARTUP_RUN']=str(a.run)
 write(a.run/'request.json',{'duration_seconds':a.seconds,'scenario':a.scenario,'prefix':prefix,'real_camera':True,'production_processes':['camerad','modeld.main(demo=False)','selfdrived(SIMULATION)','plannerd','controlsd','Tesla CarInterface.apply'],'simulated_inputs':['12m/s vehicle and changing cruise speed','private peripheral/motion/IMU packets','private deviceState.started','saved calibration and vehicle parameters','file-only actuator feedback'],'physical_panda_altered':False,'actual_vehicle_publications':0,'bench_remote_selection':False,'normal_shell_launcher':True,'observation_only_hook':'status file path','road_control_qualified':False,'ui_onroad_tested':False})
 source_paths=[Path(__file__),a.modeld_launcher,ROOT/'openpilot/sunnypilot/modeld_v2/external_host/qnn_model.py',ROOT/'openpilot/sunnypilot/modeld_v2/external_host/qnn_hotstandby.py',ROOT/'openpilot/sunnypilot/modeld_v2/external_host/opif_client.py',ROOT/'openpilot/sunnypilot/modeld_v2/external_host/opif_process.py',ROOT/'openpilot/sunnypilot/modeld_v2/external_host/opif/libopif_native.so']
 write(a.run/'source-sha256.json',{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths})
 try:subprocess.run([PYTHON,__file__,'--role','prepare','--run',str(a.run)],env=env,cwd=ROOT,check=True)
 except BaseException:
  cleanup_namespace(prefix);raise
 cpu={};irq={};children=[];logs=[];failure=None;complete=False;cooling=CoolingLease()
 def save(path):
  p=Path(path)
  if p.exists():cpu[str(p)]=p.read_text().strip()
 for i in range(4,8):save(f'/sys/devices/system/cpu/cpu{i}/online')
 for i in [0,4]:
  for n in ['scaling_governor','scaling_max_freq']:save(f'/sys/devices/system/cpu/cpufreq/policy{i}/{n}')
 from openpilot.common.gpio import get_irqs_for_action
 for action in ['kgsl-3d0','a5','cci','cpas_camnoc','cpas-cdm','csid','ife','csid-lite','ife-lite']:
  for n in get_irqs_for_action(action):
   p=Path(f'/proc/irq/{n}/smp_affinity_list');irq[str(p)]=p.read_text().strip()
 wifi_before=subprocess.check_output([str(wifi_tool),'wlan0'],text=True).strip()
 if wifi_before not in ('on','off'):raise RuntimeError('Unknown radio power-save state')
 write(a.run/'hardware-before.json',{'cpu':cpu,'irq':irq,'wifi_actual_powersave':wifi_before})
 hardware_touched=False
 def spawn(name,cmd):
  f=(a.run/(name+'.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,env=env,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);children.append((name,p));return p
 def interrupted(*unused):raise KeyboardInterrupt()
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 try:
  from openpilot.common.hardware import HARDWARE
  # Confirm actual cooling before enabling the sustained CPU/camera load.
  cooling_deadline=time.monotonic()+5
  while True:
   physical=check();cooling.refresh()
   if physical['deviceState']['fanSpeedPercentDesired']>=80 and all(p['fanPower']>=80 for p in physical['pandaStates']):break
   if time.monotonic()>=cooling_deadline:raise RuntimeError('Bench cooling did not reach the physical Panda; load not started')
   time.sleep(.1)
  write(a.run/'cooling-active.json',{'lease':cooling.value,'physical':physical})
  hardware_touched=True
  subprocess.run(['sudo','-n',str(wifi_tool),'wlan0','off'],check=True,stdout=subprocess.DEVNULL)
  actual=subprocess.check_output([str(wifi_tool),'wlan0'],text=True).strip();assert actual=='off'
  write(a.run/'wifi-active.json',{'powersave':actual,'persistent_profile_modified':False})
  HARDWARE.set_power_save(False)
  write(a.run/'hardware-active.json',{p:Path(p).read_text().strip() for p in cpu})
  active={p:Path(p).read_text().strip() for p in cpu}
  if subprocess.run(['pgrep','-x','camerad'],stdout=subprocess.DEVNULL).returncode==0:raise RuntimeError('Another camerad already running')
  spawn('feed',[PYTHON,__file__,'--role','feed','--run',str(a.run)])
  spawn('observer',[PYTHON,__file__,'--role','observe','--run',str(a.run)])
  spawn('actuator_sink',[PYTHON,__file__,'--role','actuator_sink','--run',str(a.run)])
  spawn('camerad',[str(ROOT/'openpilot/system/camerad/camerad')])
  spawn('modeld',[str(a.modeld_launcher)])
  for name,module in [('selfdrived','openpilot.selfdrive.selfdrived.selfdrived'),('plannerd','openpilot.selfdrive.controls.plannerd'),('controlsd','openpilot.selfdrive.controls.controlsd')]:
   spawn(name,[PYTHON,__file__,'--role','planner','--run',str(a.run)] if name=='plannerd' else (['env','SIMULATION=1'] if name=='selfdrived' else [])+[PYTHON,'-m',module])
  write(a.run/'processes.json',{name:p.pid for name,p in children});start=time.monotonic();last_report=0
  with (a.run/'physical-samples.jsonl').open('w',buffering=1) as f:
   while True:
    physical=check();write(a.run/'physical.json',physical)
    cooling.refresh()
    if any(Path(p).read_text().strip()!=v for p,v in active.items()):raise RuntimeError('Onroad CPU profile drift')
    for name,p in children:
     if p.poll() is not None:raise RuntimeError(name+' exited '+str(p.returncode))
    progress=json.loads((a.run/'progress.json').read_text()) if (a.run/'progress.json').exists() else {}
    control=json.loads((a.run/'actuator-progress.json').read_text()) if (a.run/'actuator-progress.json').exists() else {}
    runtime=json.loads((a.run/'runtime.json').read_text()) if (a.run/'runtime.json').exists() else {}
    if a.scenario=='baseline' and runtime.get('phase')=='latched_local':raise RuntimeError('Baseline phone output failed: '+runtime.get('failure_reason','unknown'))
    if a.scenario!='baseline' and control.get('phone_active_commands',0)>=300 and not (a.run/'inject.json').exists():
     write(a.run/'inject.json',{'fault':a.scenario,'at':time.monotonic(),'phone_active_commands_before':control['phone_active_commands']})
    if time.monotonic()-start>180 and not progress.get('first_frame_monotonic'):raise RuntimeError('No production model frames after180s')
    if progress.get('measured_seconds',0)>=a.seconds:
     if runtime.get('remote_outputs',0)<a.seconds*15:raise RuntimeError('Insufficient real phone results during normal startup')
     runtime=json.loads((a.run/'runtime.json').read_text()) if (a.run/'runtime.json').exists() else {}
     if a.scenario=='baseline' and (runtime.get('phase')!='shadow' or runtime.get('allow_control') is not False):raise RuntimeError('Unexpected production source eligibility')
     if a.scenario!='baseline' and (not (a.run/'injected.json').exists() or runtime.get('phase')!='latched_local'):raise RuntimeError('Fault injection/local fallback not demonstrated')
     complete=True;break
    if time.monotonic()-last_report>=1:
     proc_stats={}
     for name,proc in children:
      try:
       text=Path(f'/proc/{proc.pid}/stat').read_text();fields=text[text.rfind(')')+2:].split();proc_stats[name]={'cpu_ticks':int(fields[11])+int(fields[12]),'rss_bytes':int(fields[21])*os.sysconf('SC_PAGE_SIZE'),'threads':int(fields[17])}
      except (OSError,ValueError,IndexError):pass
     runtime=json.loads((a.run/'runtime.json').read_text()) if (a.run/'runtime.json').exists() else {}
     f.write(json.dumps({'timestamp_ns':physical['timestamp_ns'],'temp_c':physical['deviceState'].get('maxTempC'),'free_space_percent':physical['deviceState'].get('freeSpacePercent'),'cpu_usage_percent':physical['deviceState'].get('cpuUsagePercent'),'screen_brightness':physical['deviceState'].get('screenBrightnessPercent'),'fan_desired':physical['deviceState']['fanSpeedPercentDesired'],'panda_fan_power':[p['fanPower'] for p in physical['pandaStates']],'counts':progress.get('counts',{}),'measured_seconds':progress.get('measured_seconds',0),'runtime':runtime,'processes':proc_stats})+'\n');last_report=time.monotonic()
    time.sleep(.1)
 except BaseException as e:
  failure=type(e).__name__+': '+str(e)
  if isinstance(e,OperationalStop):write(a.run/'guard-failure.json',{'reason':str(e),'physical':e.physical})
 finally:
  signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGINT,signal.SIG_IGN)
  cleanup_stops=[]
  def keep_resources():
   try:check()
   except OperationalStop:pass
   except Exception:return
   try:cooling.refresh()
   except Exception:pass
  def stop_one(name,p):
   row={'process':name,'pid':p.pid,'forced_kill':False}
   if p.poll() is None:
    try:os.killpg(p.pid,signal.SIGINT)
    except ProcessLookupError:pass
   deadline=time.monotonic()+8
   while p.poll() is None and time.monotonic()<deadline:
    keep_resources();time.sleep(.05)
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGKILL);p.wait();row['forced_kill']=True
   row['exit_code']=p.returncode;cleanup_stops.append(row)
  for name,p in children:
   if name=='modeld':stop_one(name,p)
  for name,p in reversed(children):
   if name!='modeld':stop_one(name,p)
  write(a.run/'process-cleanup.json',cleanup_stops)
  for f in logs:f.close()
  restored=restore_hardware(cpu,irq,wifi_tool,wifi_before) if hardware_touched else {'complete':True,'not_touched':True}
  try:restored['cooling_lease_removed']=cooling.close()
  except Exception as error:restored['cooling_lease_removed']=False;restored['cooling_cleanup_error']=str(error)
  restored['complete']=restored.get('complete',False) and restored['cooling_lease_removed']
  drained=json.loads((a.run/'modeld-gpu-drained.json').read_text()) if (a.run/'modeld-gpu-drained.json').exists() else {}
  restored['modeld_gpu_drained']=drained
  restored['complete']=restored.get('complete',False) and drained.get('complete',False) and not any(row['forced_kill'] for row in cleanup_stops)
  write(a.run/'cleanup.json',restored)
  try:namespace_cleanup=cleanup_namespace(prefix)
  except Exception as e:namespace_cleanup={'error':str(e)}
  progress=json.loads((a.run/'progress.json').read_text()) if (a.run/'progress.json').exists() else {}
  runtime=json.loads((a.run/'runtime.json').read_text()) if (a.run/'runtime.json').exists() else {}
  write(a.run/'result.json',{'completed_requested_duration':complete,'failure':failure,'progress':progress,'runtime':runtime,'hardware_restored':restored,'namespace_cleanup':namespace_cleanup,'road_control_qualified':False,'actual_vehicle_publications':0})
  print(json.dumps({'run':str(a.run),'completed':complete,'failure':failure,'frames':progress.get('counts',{}),'remote_state':runtime.get('phase')}),flush=True)
 if failure:raise SystemExit(1)

def preflight(a):
 print(json.dumps(guard()()))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--role',choices=['supervise','prepare','feed','observe','actuator_sink','preflight','planner'],default='supervise');parser.add_argument('--run',type=Path,required=True);parser.add_argument('--seconds',type=int,default=40);parser.add_argument('--phone',default='172.16.1.129');parser.add_argument('--scenario',choices=['baseline','disconnect','stale'],default='baseline');parser.add_argument('--usb',action='store_true');parser.add_argument('--modeld-launcher',type=Path,default=ROOT/'openpilot/sunnypilot/modeld_v2/modeld');a=parser.parse_args()
 if not 10<=a.seconds<=3600:parser.error('Bounded10..3600 second run required')
 globals()[a.role if a.role!='supervise' else 'supervise'](a)
