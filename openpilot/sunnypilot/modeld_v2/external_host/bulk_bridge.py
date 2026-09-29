"""Carry authenticated host packets over the existing tested Jetlink USB framing."""
import argparse
import signal
import socket
import struct
import threading
import time
from .wire import HEADER,MAX_PAYLOAD,exact
from jetlink.transport.base import LinkError, LinkTimeout
from jetlink.transport.priority import background_thread

WRAP_TYPE=1800

def bridge(sock,link,*,host):
  background_thread()
  stop=threading.Event();failures=[]
  def fail(error):
    failures.append(str(error));stop.set()
    try:sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
  def sending():
    background_thread()
    try:
      index=0
      while not stop.is_set():
        header=exact(sock,HEADER.size,time.monotonic()+30)
        kind,size,seq=HEADER.unpack(header)
        if size>MAX_PAYLOAD:raise RuntimeError('Oversize host packet')
        trailer=0 if host and index==0 and kind==1 else 32
        payload=exact(sock,size+trailer,time.monotonic()+5)
        link.send(WRAP_TYPE,index,(header,payload),timeout=5);index+=1
    except Exception as error:fail(error)
  t=threading.Thread(target=sending,daemon=True);t.start()
  try:
    index=0
    while not stop.is_set():
      try:msg=link.recv(timeout=.5)
      except LinkTimeout:continue
      if msg.msg_type!=WRAP_TYPE or msg.seq!=index or len(msg.payload)>MAX_PAYLOAD+48:raise RuntimeError('USB wrapper identity mismatch')
      packet=bytes(msg.payload);sock.sendall(packet);index+=1
  except Exception as error:fail(error)
  finally:
    stop.set()
    try:sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
    sock.close();t.join(timeout=6)
    if not t.is_alive():link.close()
  if failures:raise RuntimeError(failures[0])

def gadget_socket(mount='/dev/ffs-jetlink',gadget=None,udc=None):
  from jetlink.transport.ffs import FfsTransport
  link=FfsTransport(mount,gadget=gadget,udc=udc)
  client,worker=socket.socketpair();worker.settimeout(5)
  def serve():
    try:bridge(worker,link,host=False)
    except Exception:pass
  threading.Thread(target=serve,daemon=True).start()
  return client

def main():
  from jetlink.transport.usbbulk import UsbBulkTransport
  p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=5599);a=p.parse_args()
  def stop(*_):raise KeyboardInterrupt()
  signal.signal(signal.SIGTERM,stop)
  link=None
  print('WAIT_USB',flush=True)
  try:
    while link is None:
      try:link=UsbBulkTransport.open()
      except LinkError:time.sleep(.25)
    sock=socket.create_connection(('127.0.0.1',a.port),timeout=5);sock.settimeout(5)
    print('USB_CONNECTED',flush=True);owned=link;link=None;bridge(sock,owned,host=True)
  finally:
    if link is not None:link.close()
if __name__=='__main__':main()
