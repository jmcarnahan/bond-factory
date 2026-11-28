"""Test-only entry that behaves like ``python -m roof_measure._child`` but whose pipeline dies in a chosen way.

Not a test module (pytest ignores the name). ``test_child_crash.py`` points ``_isolate._child_argv`` at it. The pipeline dies with a real SIGSEGV (a read of
address 0). The real ``_child.main`` runs, so its faulthandler setup is what is under test. The pipeline reports the
model stage first, as the real one does.
"""

import ctypes
import sys

from roof_measure import _child, pipeline


def die(*_args, on_stage=None, **_kwargs):
    if on_stage is not None:
        on_stage("model")
    ctypes.string_at(0)


pipeline.run_pipeline = die  # _child.main imports run_pipeline from here when it runs

sys.exit(_child.main())
