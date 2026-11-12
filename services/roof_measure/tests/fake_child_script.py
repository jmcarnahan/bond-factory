"""Stand-in for ``roof_measure._child`` in the isolate tests (not a test module: pytest ignores the name).

Reads the request line and acts on ``req["address"]`` as the command. Writes its pid to ``<work_dir>/pid`` first.
"""

import json
import os
import sys
import time
from pathlib import Path

req = json.loads(sys.stdin.readline())
Path(req["work_dir"], "pid").write_text(str(os.getpid()))
cmd = req["address"]


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if cmd in ("hang", "abort"):
    emit({"t": "stage", "name": "model"})
    if cmd == "abort":
        os.abort()
    time.sleep(600)
elif cmd == "stderr-exit-3":
    sys.stderr.write("boom-marker\n")
    sys.stderr.flush()
    sys.exit(3)
elif cmd == "echo-env":
    emit({"t": "ok", "envelope": {"_env": sorted(os.environ)}})
elif cmd == "echo-key":
    emit({"t": "ok", "envelope": {"_key": req["runtime"]["anthropic_api_key"]}})
elif cmd == "stray-stdout":
    sys.stdout.write("42\n[1,2]\njunk-without-newline\n")
    sys.stdout.flush()
    emit({"t": "stage", "name": "model"})
    emit({"t": "ok", "envelope": {"fine": True}})
elif cmd == "nan":
    sys.stdout.write('{"t": "ok", "envelope": {"x": NaN}}\n')
    sys.stdout.flush()
