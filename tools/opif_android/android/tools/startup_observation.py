"""Private normal-startup observation and graceful test shutdown only."""
import atexit
import json
import os
from pathlib import Path
import signal
import sys

if (os.environ.get('OPENPILOT_PREFIX', '').startswith('qnnbench_')
        and os.environ.get('NORMAL_STARTUP_RUN') and '--worker-fd' not in sys.argv):
    from openpilot.sunnypilot.modeld_v2.external_host import qnn_hotstandby
    run = Path(os.environ['NORMAL_STARTUP_RUN'])
    qnn_hotstandby.STATUS_PATH = run / 'runtime.json'
    stopping = False
    original_run = qnn_hotstandby.QnnHotStandby.run
    original_init = qnn_hotstandby.QnnHotStandby.__init__

    def request_stop(*_):
        global stopping
        stopping = True

    def at_frame_boundary(self, *args, **kwargs):
        if stopping:
            raise KeyboardInterrupt()
        return original_run(self, *args, **kwargs)

    def drain():
        from tinygrad import Device
        result = {'complete': False, 'synchronized': []}
        try:
            for name in tuple(Device._opened_devices):
                if name.startswith('QCOM'):
                    Device[name].synchronize()
                    result['synchronized'].append(name)
            result['complete'] = True
        except Exception as error:
            result['error'] = str(error)
        (run / 'modeld-gpu-drained.json').write_text(json.dumps(result) + '\n')

    def initialized(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        atexit.register(drain)
        signal.signal(signal.SIGINT, request_stop)

    qnn_hotstandby.QnnHotStandby.__init__ = initialized
    qnn_hotstandby.QnnHotStandby.run = at_frame_boundary
