"""Serialize finite readiness probes, never the frame stream or daemon lifetime."""
from contextlib import contextmanager
import fcntl
import os
import time

PATH='/dev/shm/qnn-readiness-probe.lock'


@contextmanager
def exclusive_probe(timeout=8.):
  fd=os.open(PATH,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  end=time.monotonic()+timeout
  try:
    while True:
      try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        break
      except BlockingIOError:
        if time.monotonic()>=end:
          raise TimeoutError('Another phone readiness probe is still active')
        time.sleep(min(.02,max(0,end-time.monotonic())))
    yield
  finally:
    os.close(fd)
