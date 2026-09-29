#!/usr/bin/env python3
"""Real native OPIF socket E2E; synthetic accelerator only. Writes packet evidence."""
import argparse, hashlib, json, pathlib, socket, struct, subprocess, time
ROOT=pathlib.Path(__file__).resolve().parents[1]
def crc(data):
 c=0xffffffff
 for b in data:
  c^=b
  for _ in range(8): c=(c>>1)^(0x82f63b78 if c&1 else 0)
 return c^0xffffffff
def encode(kind,sid,rid,body):
 size=1192; count=max(1,(len(body)+size-1)//size); checksum=crc(body)
 packet=b''
 for i in range(count):
  part=body[i*size:(i+1)*size]
  h=struct.pack('<4sBBHHHQQHHII',b'OPIF',1,kind,0,40,len(part),sid,rid,i,count,len(body),checksum)
  packet+=struct.pack('<I',len(h)+len(part))+h+part
 return packet
def send(s,kind,sid,rid,body):s.sendall(encode(kind,sid,rid,body))
def take(s,n):
 result=b''
 while len(result)<n:
  more=s.recv(n-len(result))
  if not more: raise EOFError()
  result+=more
 return result
def receive(s,wanted):
 chunks={}
 while True:
  p=take(s,struct.unpack('<I',take(s,4))[0]); h=struct.unpack('<4sBBHHHQQHHII',p[:40]);kind=h[2];rid=h[7]
  if kind not in wanted: continue
  key=(kind,rid); entry=chunks.setdefault(key,{})
  entry[h[8]]=p[40:]
  if len(entry)==h[9]:
   body=b''.join(entry[i] for i in range(h[9]));assert len(body)==h[10] and crc(body)==h[11]
   return kind,h[6],rid,body

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--baseline',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 binary=a.out/'protocol-fixture';cmd=['c++','-std=c++17','-pthread','-O2','-I'+str(ROOT/'native'),str(ROOT/'native/opif_protocol.cpp'),str(ROOT/'e2e/protocol_fixture.cpp'),'-o',str(binary)]
 subprocess.run(cmd,check=True);server=subprocess.Popen([str(binary)],stdout=subprocess.PIPE,text=True);port=int(server.stdout.readline()); rows=[]; bodies={}
 try:
  for encoding in (0,2):
   with socket.create_connection(('127.0.0.1',port),timeout=5) as s:
    start=struct.pack('<BBBBHIH',0,0,encoding,0,1232,0,0);send(s,1,0,77,start);kind,sid,rid,ready=receive(s,{0x81,255})
    if kind==255:
     rows.append({'encoding':encoding,'error':'START rejected','body':ready.hex()});continue
    expected=18452 if encoding==0 else 2068
    assert ready[3]==encoding and struct.unpack_from('<I',ready,12)[0]==expected
    requests=[]
    for rid in (1,2):
     body=struct.pack('<BBBBHHffQII',0,0,0,0,1 if rid==1 else 0,0,.1,.1,1000000*rid,393216,393216)+bytes(393216)
     requests.append(encode(16,sid,rid,body))
    for rid,request in enumerate(requests,1):
     s.sendall(request)
     if rid==1:receive(s,{6})
    got={}
    for _ in range(2):
     kind,rsid,rid,result=receive(s,{0x90,255});assert kind==0x90 and rsid==sid
     assert result[1]==encoding and result[2]==(2 if encoding==2 else 0)
     assert struct.unpack_from('<I',result,4)[0]==expected and len(result)==24+4*expected
     got[rid]=result; (a.out/f'result-{encoding}-{rid}.bin').write_bytes(result)
    queue=struct.unpack_from('<I',got[2],12)[0]
    # Repeat ID must replay exact terminal and never advance model state.
    query=struct.pack('<BBHII',0x90,0,0,0,0);send(s,4,sid,2,query);_,_,_,replay=receive(s,{0x90});assert replay==got[2]
    nanbody=struct.pack('<BBBBHHffQII',0,0,7,0,0,0,.1,.1,3000000,393216,393216)+bytes(393216);send(s,16,sid,3,nanbody);nk,_,_,nb=receive(s,{0x90,255})
    rows.append({'encoding':encoding,'queue_us_second':queue,'positive_queue':queue>1000,'nonfinite_hidden_rejected':nk==255,'replay_identical':True,'payload_bytes':len(got[1])-24})
    bodies[encoding]=got[1][24:];send(s,2,sid,99,b'');receive(s,{0x82});time.sleep(.1)
  compact_equal=(2 in bodies and bodies[2]==bodies[0][:2066*4]+bodies[0][18450*4:])
  passed=len(rows)==2 and compact_equal and all(x.get('positive_queue') and x.get('nonfinite_hidden_rejected') for x in rows)
  evidence={'fixture':'synthetic acceleration; real production TCP/OPIF server','cases':rows,'compact_exact_bytes':compact_equal,'passed':passed,'command':'python3 android/e2e/protocol_roundtrip.py --out <directory>','source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'native/opif_protocol.cpp',ROOT/'e2e/protocol_fixture.cpp')}}
  (a.out/'result.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence));return 0 if passed or a.baseline else 1
 finally:server.terminate();server.wait(timeout=5)
if __name__=='__main__':raise SystemExit(main())
