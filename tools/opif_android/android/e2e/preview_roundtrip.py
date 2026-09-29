#!/usr/bin/env python3
"""Production Kotlin parser/matcher/projector over real UDP, synthetic image metadata."""
import argparse,json,pathlib,socket,struct,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from fetch_android_sdk import fetch_tools
from fetch_kotlin import fetch_kotlin
p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--tools',type=pathlib.Path,default=pathlib.Path('/private/tmp/opif-install-20260926/tools'));a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
t=fetch_tools(a.tools);k=fetch_kotlin(a.tools);jar=a.out/'preview.jar'
subprocess.run([str(k['compiler']),'-jvm-target','1.8','-no-stdlib','-no-reflect','-classpath',str(k['stdlib']),'-d',str(jar),str(ROOT/'app/src/main/kotlin/com/example/openpilotinference/android/SpPath.kt'),str(ROOT/'e2e/sp_path_fixture.kt')],check=True)
proc=subprocess.Popen([str(pathlib.Path(t['java_home'])/'bin/java'),'-cp',str(jar)+':'+str(k['stdlib']),'com.example.openpilotinference.android.Sp_path_fixtureKt',str(a.out/'path.svg')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);port=int(proc.stdout.readline())
header=struct.pack('<4sBBHQQQQQI IfffHH',b'SPR1',1,2,3|8|16,10,77,1,12,999,1,1,70.,1.22,1.,100,33)
# Production calibrated-frame axes: image right=+y, image down=+z.
left=(256.,910.,0.,47.6,0.,910.,1.,0.,0.);right=(256.,455.,0.,151.8,0.,455.,1.,0.,0.)
points=[v for i in range(33) for v in (10.+2*i,0.002*i*i,0.)]
body=header+struct.pack('<18f',*left,*right)+struct.pack('<99f',*points)+struct.pack('<33f',*[0.]*33);assert len(body)==672
(a.out/'route.bin').write_bytes(body)
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.sendto(body,('127.0.0.1',port))
out,err=proc.communicate(timeout=15);print(out,err);assert proc.returncode==0
(a.out/'result.json').write_text(out)
