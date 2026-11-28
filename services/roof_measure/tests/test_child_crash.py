"""A child that dies of a native crash: the parent's error names the signal and shows the faulthandler traceback."""

import copy
import pickle
import signal
import sys
from pathlib import Path

import pytest
from house_helpers import house

import roof_measure._isolate as isolate
import roof_measure.library
from roof_measure.library import MeasureError, measure

ENTRY = Path(__file__).with_name("crash_child_entry.py")


@pytest.fixture(autouse=True)
def _hang_guard():
    def handler(signum, frame):
        raise TimeoutError("test hung")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(60)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.fixture
def crashing_child(monkeypatch):
    monkeypatch.setattr(isolate, "_child_argv", lambda: [sys.executable, "-P", str(ENTRY)])
    monkeypatch.setattr(roof_measure.library, "KILL_GRACE_S", 1.0)


def run(tmp_path, **kw):
    args = {"method": "lidar_skeleton", "cache_dir": tmp_path / "cache", "points_path": house(tmp_path),
            "work_dir": tmp_path / "work"}
    return measure("100 Example Ave, Sampletown, CA 90000", **(args | kw))


def test_segfaulting_child_yields_a_message_that_says_so(tmp_path, crashing_child):
    with pytest.raises(MeasureError) as e:
        run(tmp_path)
    msg = e.value.message
    assert e.value.code == "measurement_failed" and not e.value.retryable
    assert "Segmentation fault" in msg and "SIGSEGV" in msg and "-11" in msg
    assert "Fatal Python error" in msg  # faulthandler wrote its report into child.stderr and the tail has it


def test_the_crash_is_a_ChildCrashed_with_the_signal_number(tmp_path, crashing_child):
    with pytest.raises(isolate.ChildCrashed) as e:
        run(tmp_path)
    assert e.value.signal_number == signal.SIGSEGV and isinstance(e.value, MeasureError)


def test_child_stderr_file_keeps_the_python_traceback(tmp_path, crashing_child):
    with pytest.raises(MeasureError):
        run(tmp_path)
    text = (tmp_path / "work" / "child.stderr").read_text()
    assert "Fatal Python error: Segmentation fault" in text and "crash_child_entry.py" in text


def test_the_stage_hook_relays_every_stage():
    from roof_measure import _child

    emitted = []
    hook = _child._stage_hook(emit=emitted.append)
    for name in ("geocode", "model"):
        hook(name)
    assert emitted == [{"t": "stage", "name": "geocode"}, {"t": "stage", "name": "model"}]


def test_a_normal_nonzero_exit_is_not_a_crash(tmp_path, monkeypatch):
    fake = Path(__file__).with_name("fake_child_script.py")
    monkeypatch.setattr(isolate, "_child_argv", lambda: [sys.executable, "-P", str(fake)])
    with pytest.raises(MeasureError) as e:
        measure("stderr-exit-3", lat=1.0, lng=1.0, method="lidar_skeleton",
                cache_dir=tmp_path / "cache", points_path=house(tmp_path))
    assert not isinstance(e.value, isolate.ChildCrashed) and "exited with code 3" in e.value.message


@pytest.mark.parametrize("code, name", [(-6, "SIGABRT"), (-9, "SIGKILL"), (-11, "SIGSEGV"), (3, None)])
def test_exit_text_names_the_signal(code, name):
    text = isolate._exit_text(code)
    assert text.startswith(f"exited with code {code}") and (name is None or name in text)


def test_stderr_tail_starts_at_the_fatal_line(tmp_path):
    p = tmp_path / "e"
    p.write_text("noise\n" * 30 + "Fatal Python error: Segmentation fault\n\nCurrent thread 0x1 (most recent call first):\n"
                 + "".join(f'  File "f{i}.py", line {i}\n' for i in range(40)))
    tail = isolate._stderr_tail(p)
    assert tail.startswith("; stderr: Fatal Python error: Segmentation fault") and "noise" not in tail


def test_child_crashed_survives_copy_and_pickle():
    """Same positional signature as MeasureError, so copy and pickle (multiprocessing) rebuild it."""
    err = isolate.ChildCrashed("measurement_failed", "the process died", False, signal_number=11)
    for twin in (copy.copy(err), copy.deepcopy(err), pickle.loads(pickle.dumps(err))):
        assert isinstance(twin, isolate.ChildCrashed)
        assert (twin.code, twin.message, twin.retryable, twin.signal_number) == (
            "measurement_failed", "the process died", False, 11)
    plain = isolate.ChildCrashed()
    assert plain.code == "measurement_failed" and plain.signal_number == 0
    assert isolate.ChildCrashed("timeout", "x", True).retryable is True  # positional like MeasureError
