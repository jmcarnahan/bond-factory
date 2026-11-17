"""Test-only entry that behaves like ``python -m roof_measure._child`` but whose pipeline dies in a chosen way.

Not a test module (pytest ignores the name). ``test_child_crash.py`` and ``test_agent_fallback.py`` point
``_isolate._child_argv`` at it. ``argv[1]`` is the mode: ``crash`` (default; a real SIGSEGV, a read of address 0) or
``hang`` (a native-style hang: the stage is reported, then the process sleeps). The real ``_child.main`` runs, so its
faulthandler setup and its agent-hang timer are what is under test. The pipeline reports the model stage first, as
the real one does.
"""

import ctypes
import sys
import time

from roof_measure import _child, pipeline

MODE = sys.argv[1] if len(sys.argv) > 1 else "crash"


def die(*_args, on_stage=None, **_kwargs):
    if on_stage is not None:
        on_stage("model")
    if MODE == "hang":
        time.sleep(600)
    ctypes.string_at(0)


pipeline.run_pipeline = die  # _child.main imports run_pipeline from here when it runs
if MODE == "hang":
    _child.AGENT_HANG_SHARE = 0.05  # the real share is 0.6; shrink it so the test does not wait half a minute
    _child.AGENT_HANG_SLACK_S = 0.5

sys.exit(_child.main())
