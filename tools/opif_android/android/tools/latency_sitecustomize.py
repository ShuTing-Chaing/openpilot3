"""Select temporary modules in a private bench only, including its I/O worker."""
import os
import json
from pathlib import Path
import sys

if os.environ.get('OPENPILOT_PREFIX', '').startswith('qnnbench_') and os.environ.get('OPIF_LATENCY_CODE'):
    if '--worker-fd' in sys.argv:
        # One startup identity record, before inference; no per-frame file I/O.
        (Path(os.environ['OPIF_LATENCY_RUN']) / 'io-process-identity.json').write_text(json.dumps(
            {'worker_pid': os.getpid(), 'parent_pid': os.getppid()}) + '\n')
    import openpilot.sunnypilot.modeld_v2.external_host as host
    directory = Path(os.environ['OPIF_LATENCY_CODE']) / 'openpilot/sunnypilot/modeld_v2/external_host'
    host.__path__.insert(0, str(directory))
    import openpilot.sunnypilot.modeld_v2.external_host.opif as opif
    opif.__path__.insert(0, str(directory / 'opif'))
    if '--worker-fd' in sys.argv and os.environ.get('OPIF_LATENCY_IO_CORES') == '4,5':
        from openpilot.sunnypilot.modeld_v2.external_host import priority
        original_background = priority.background_thread
        def io_background():
            original_background()
            os.sched_setaffinity(0, {4, 5})
        priority.background_thread = io_background
    # Reuse the already exercised status-only observation and GPU drain.
    import runpy
    runpy.run_path(str(Path(os.environ['OPIF_LATENCY_TOOLS']) / 'startup_observation.py'))
