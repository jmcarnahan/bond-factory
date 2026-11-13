"""Stub adopter check: the overlay ran against libs in the bond checkout, in a temp copy of the app."""
import os
import sys

log = open("overlay.log").read().split()
assert log, "overlay.log is empty: the overlay did not run"
for lib in log:
    assert os.path.isdir(lib), f"overlay recorded a missing directory: {lib}"
    assert os.path.basename(os.path.dirname(lib)) == "libs", f"not under <bond>/libs: {lib}"
if "--isolated" in sys.argv:
    here = os.path.realpath(os.getcwd())
    assert "adopter-" in here, f"cwd is not in the temp copy: {here}"
    print("cwd", here)
print("ok", len(log), "libs")
