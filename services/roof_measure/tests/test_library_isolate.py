"""measure(isolate=True): a real child on the blocks fixture, and a fake child for the failure modes; zero network."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import pytest
from conftest import FIXTURES

import roof_measure._child as child_mod
import roof_measure._isolate
import roof_measure.library
from roof_measure.library import MeasureError, measure

ADDR = "100 Example Ave, Sampletown, CA 90000"
BLOCKS = FIXTURES / "site1_blocks.json"
FAKE_CHILD = Path(__file__).with_name("fake_child_script.py")


@pytest.fixture(autouse=True)
def _hang_guard():
    """A removed kill must fail one test in 60 s, not block the suite for the child's 600 s sleep."""
    def handler(signum, frame):
        raise TimeoutError("test hung")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(60)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.fixture
def fake_child(monkeypatch):
    monkeypatch.setattr(roof_measure._isolate, "_child_argv", lambda: [sys.executable, "-P", str(FAKE_CHILD)])
    monkeypatch.setattr(roof_measure.library, "KILL_GRACE_S", 1.0)


def call(tmp_path, addr=ADDR, **kw):
    args = {"method": "lidar_skeleton", "verify": False, "cache_dir": tmp_path / "cache", "blocks_path": BLOCKS}
    return measure(addr, **(args | kw))


def gone(pid: int) -> bool:
    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def pid_of(work: Path) -> int:
    return int((work / "pid").read_text())


def test_happy_path_and_stage_thread(tmp_path):
    seen, threads = [], set()

    def cb(name):
        seen.append(name)
        threads.add(threading.get_ident())
    env = call(tmp_path, on_stage=cb)
    assert env["contract"] == "bond.roof_model/0.2" and env["totals"]["area_sqft"] > 0
    assert seen == ["model", "render"] and threads == {threading.get_ident()}


def test_relative_paths_are_resolved_for_the_child(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shutil.copy(BLOCKS, tmp_path / "b.json")
    env = measure(ADDR, method="lidar_skeleton", verify=False, cache_dir="relcache", work_dir="relwork",
                  blocks_path="b.json", isolate=True)
    assert env["contract"] == "bond.roof_model/0.2"
    assert any(p.name.endswith("_model.json") for p in (tmp_path / "relwork").iterdir())
    assert not (tmp_path / "relwork" / "relwork").exists() and (tmp_path / "relcache").is_dir()


def test_hang_is_killed_at_the_deadline_plus_grace(tmp_path, fake_child):
    seen, work = [], tmp_path / "w"
    t0 = time.monotonic()
    with pytest.raises(MeasureError) as e:
        call(tmp_path, "hang", deadline_s=2, on_stage=seen.append, work_dir=work)
    assert e.value.code == "timeout" and e.value.retryable is True and "stopped after" in e.value.message
    assert time.monotonic() - t0 < 6
    assert seen == ["model"] and gone(pid_of(work))


def test_crash_is_measurement_failed_and_the_temp_dir_goes(tmp_path, fake_child, monkeypatch):
    made, real = [], tempfile.mkdtemp
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **k)) or made[-1])
    seen = []
    t0 = time.monotonic()
    with pytest.raises(MeasureError) as e:
        call(tmp_path, "abort", on_stage=seen.append)
    assert e.value.code == "measurement_failed" and e.value.retryable is False
    assert "exited with code" in e.value.message and "-6" in e.value.message
    assert time.monotonic() - t0 < 5 and seen == ["model"] and not Path(made[0]).exists()


def test_child_environment_is_a_whitelist(tmp_path, fake_child, monkeypatch):
    monkeypatch.setenv("ROOF_TEST_SECRET", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    env = call(tmp_path, "echo-env", work_dir=tmp_path / "w")["_env"]
    assert "ROOF_TEST_SECRET" not in env and "ANTHROPIC_API_KEY" not in env
    assert "OMP_NUM_THREADS" in env and "PATH" in env


def test_a_child_error_reply_keeps_its_code(tmp_path):
    with pytest.raises(MeasureError) as e:
        call(tmp_path, deadline_s=0.001)
    assert e.value.code == "timeout" and e.value.retryable is True
    assert "deadline exceeded" in e.value.message and "stopped after" not in e.value.message


def test_the_stderr_tail_reaches_the_crash_message(tmp_path, fake_child):
    with pytest.raises(MeasureError) as e:
        call(tmp_path, "stderr-exit-3", work_dir=tmp_path / "w")
    assert e.value.code == "measurement_failed"
    assert "exited with code 3" in e.value.message and "boom-marker" in e.value.message


def test_the_anthropic_key_reaches_the_child_and_none_stays_none(tmp_path, fake_child, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    assert call(tmp_path, "echo-key", work_dir=tmp_path / "w1", anthropic_api_key="arg-key")["_key"] == "arg-key"
    assert call(tmp_path, "echo-key", work_dir=tmp_path / "w2")["_key"] is None


def test_stray_stdout_lines_are_dropped(tmp_path, fake_child):
    seen = []
    env = call(tmp_path, "stray-stdout", work_dir=tmp_path / "w", on_stage=seen.append)
    assert env == {"fine": True} and seen == ["model"]


def test_non_finite_numbers_in_the_envelope_fail_cleanly(tmp_path, fake_child):
    with pytest.raises(MeasureError) as e:
        call(tmp_path, "nan", work_dir=tmp_path / "w")
    assert e.value.code == "measurement_failed" and "non-finite" in e.value.message


def test_the_real_child_emit_replaces_a_nan_envelope_with_an_error_reply(monkeypatch):
    import io

    out = io.StringIO()
    monkeypatch.setattr(child_mod, "_PROTO", out)
    child_mod._emit({"t": "ok", "envelope": {"x": float("nan")}})
    msg = json.loads(out.getvalue())
    assert msg["t"] == "err" and msg["error"]["code"] == "measurement_failed"
    assert "non-finite" in msg["error"]["message"]


def test_the_real_child_keeps_library_prints_off_the_protocol_stream(tmp_path):
    code = textwrap.dedent("""
        import sys, json
        from types import SimpleNamespace
        import roof_measure.pipeline as p
        def fake(*a, **k):
            print("stray", end="")
            return SimpleNamespace(envelope={"a": 1})
        p.run_pipeline = fake
        from roof_measure import _child
        sys.exit(_child.main())
    """)
    req = {"address": "x", "lat_lng": None, "method": "lidar_skeleton", "verify": False, "force": False,
           "deadline_s": 30.0, "work_dir": str(tmp_path), "blocks_path": None, "solar_fixture": None,
           "runtime": {"cache_dir": str(tmp_path), "anthropic_api_key": None, "google_solar_api_key": None,
                       "overpass_urls": None, "footprint_stage_s": None}}
    res = subprocess.run([sys.executable, "-P", "-c", code], input=json.dumps(req) + "\n", capture_output=True,
                         text=True, timeout=60, check=False)
    assert res.returncode == 0, res.stderr[-500:]
    msgs = [json.loads(line) for line in res.stdout.splitlines()]
    assert msgs == [{"t": "ok", "envelope": {"a": 1}}] and "stray" in res.stderr


def test_the_child_exits_when_its_parent_dies(tmp_path):
    child = textwrap.dedent("""
        import time
        from roof_measure import _child
        _child._start_watchdog()
        print("ready", flush=True)
        time.sleep(600)
    """)
    parent = textwrap.dedent(f"""
        import os, subprocess, sys
        p = subprocess.Popen([sys.executable, "-P", "-c", {child!r}], stdout=subprocess.PIPE, text=True)
        assert p.stdout.readline().strip() == "ready"
        print(p.pid, flush=True)
        os._exit(0)
    """)
    res = subprocess.run([sys.executable, "-c", parent], capture_output=True, text=True, timeout=30, check=False)
    assert res.returncode == 0, res.stderr[-500:]
    pid = int(res.stdout.split()[0])
    try:
        assert gone(pid)  # polls for 4 s; the watchdog polls every 0.5 s
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
