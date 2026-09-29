"""Temporary, bounded, thread-local C3 bench trace. No per-frame disk writes."""
import atexit
import json
import os
import resource
from pathlib import Path
import struct
import threading
import time

NAMES = 'WORKER SESSION SUBMIT PAIR_MAIN PAIR_EXTRA TICK LOCAL_BEGIN LOCAL_END IPC_SUBMIT WORKER_TAKE WIRE_SUBMIT SEND_QUEUED SEND_DONE FULL PARSED POLL_BEGIN POLL_RESULT POLL_END SELECT_BEGIN SELECT_END IPC_FORWARD PARENT_IPC AVAILABLE MODEL_TAKE CHECKED VALID ERROR CLOSED'.split()
CODES = {name: i + 1 for i, name in enumerate(NAMES)}
ESSENTIAL = set('WORKER SESSION SUBMIT PAIR_MAIN PAIR_EXTRA TICK FULL AVAILABLE CHECKED VALID ERROR CLOSED'.split())
MODE = os.getenv('OPIF_LATENCY_MODE', 'off')
ENABLED = MODE in ('minimal', 'full') and os.getenv('OPENPILOT_PREFIX', '').startswith('qnnbench_')
CAPACITY = (int(os.getenv('OPIF_LATENCY_SECONDS', '60')) + 240) * 1200
RECORD = struct.Struct('<8Q')
local = threading.local()
buffers = []
errors = []
identities = {}
link_id = os.getpid()
started = (time.clock_gettime_ns(time.CLOCK_BOOTTIME), time.monotonic_ns())


def emit(name, request=0, a=0, b=0, c=0, d=0):
    if not ENABLED or MODE == 'minimal' and name not in ESSENTIAL:
        return
    state = getattr(local, 'state', None)
    if state is None:
        state = [threading.get_ident(), threading.current_thread().name, [], 0]
        local.state = state
        buffers.append(state)
    if len(state[2]) >= CAPACITY:
        state[3] += 1
        return
    state[2].append(RECORD.pack(time.clock_gettime_ns(time.CLOCK_BOOTTIME), CODES[name], link_id,
                               int(request), int(a), int(b), int(c), int(d)))


def bind(pid):
    global link_id
    link_id = int(pid)
    emit('WORKER', 0, os.getpid(), pid)


def capture(seq, context):
    if not ENABLED:
        return
    main, extra = context['meta_main'], context['meta_extra']
    if len(identities) >= CAPACITY:
        raise RuntimeError('latency trace identity capacity exceeded')
    identities[(main.frame_id, main.timestamp_eof)] = seq
    emit('SUBMIT', seq, main.frame_id, main.timestamp_eof)
    emit('PAIR_MAIN', seq, main.frame_id, main.timestamp_sof, main.timestamp_eof)
    emit('PAIR_EXTRA', seq, extra.frame_id, extra.timestamp_sof, extra.timestamp_eof)


def rid(context):
    meta = context['meta_main']
    return identities.get((meta.frame_id, meta.timestamp_eof), 0)


def attach_queue(q):
    if not ENABLED:
        return
    actual = q._put
    def put(value):
        actual(value)
        seq, fid, eof, _, _ = value
        emit('AVAILABLE', seq, fid, eof, q._qsize())
    q._put = put


def error(value):
    if ENABLED:
        index = len(errors) + 1
        errors.append({'index': index, 'message': str(value), 'type': type(value).__name__})
        emit('ERROR', 0, index)


def flush():
    if not ENABLED or not buffers:
        return
    directory = Path(os.environ['OPIF_LATENCY_RUN']) / 'trace'
    directory.mkdir(exist_ok=True)
    meta = {'pid': os.getpid(), 'link_id': link_id, 'mode': MODE, 'capacity_per_thread': CAPACITY,
            'record_format': '<8Q', 'fields': ['boottime_ns', 'event', 'worker_pid', 'request_id', 'a', 'b', 'c', 'd'],
            'codes': CODES, 'errors': errors, 'clock_start_boottime_monotonic_ns': started,
            'process_cpu_seconds': list(os.times())[:2], 'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'clock_end_boottime_monotonic_ns': [time.clock_gettime_ns(time.CLOCK_BOOTTIME), time.monotonic_ns()], 'threads': []}
    for tid, name, records, dropped in buffers:
        file = f'{os.getpid()}-{tid}.bin'
        (directory / file).write_bytes(b''.join(records))
        meta['threads'].append({'file': file, 'name': name, 'records': len(records), 'dropped': dropped})
    (directory / f'{os.getpid()}.json').write_text(json.dumps(meta, indent=2) + '\n')


atexit.register(flush)
