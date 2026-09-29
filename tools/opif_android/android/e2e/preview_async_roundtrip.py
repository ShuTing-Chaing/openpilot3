#!/usr/bin/env python3
import argparse,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from fetch_android_sdk import fetch_tools
from fetch_kotlin import fetch_kotlin
p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--baseline',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
t=fetch_tools(pathlib.Path('/private/tmp/opif-install-20260926/tools'));k=fetch_kotlin(pathlib.Path('/private/tmp/opif-install-20260926/tools'));src=ROOT/'app/src/main/kotlin/com/example/openpilotinference/android';jar=a.out/'preview.jar'
subprocess.run([str(k['compiler']),'-jvm-target','1.8','-no-stdlib','-no-reflect','-classpath',str(k['stdlib']),'-d',str(jar),str(src/'SpPath.kt'),str(src/'InputPreview.kt'),str(ROOT/'e2e/preview_async_fixture.kt'),*map(str,(ROOT/'e2e/preview_stubs').glob('*.kt'))],check=True)
subprocess.run([str(pathlib.Path(t['java_home'])/'bin/java'),'-cp',str(jar)+':'+str(k['stdlib']),'com.example.openpilotinference.android.Preview_async_fixtureKt',str(a.out)],check=True,timeout=15)
r=json.loads((a.out/'result.json').read_text());raise SystemExit(0 if r['passed'] or a.baseline else 1)
