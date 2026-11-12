"""scripts/sweep_interval.py runs on `bond_jobs.run_schedule`: two entries, logging configured, SIGTERM-safe."""

import importlib.util
import json
import threading
from pathlib import Path

import pytest
from bond_jobs import Every, run_schedule
from connections_util import headers
from todo_util import notices_of, timed

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sweep_interval.py"


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("sweep_interval_gaps", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def h(client):
    return headers(client)


def test_the_loop_is_two_schedules_the_sweep_every_n_seconds_and_the_prune_hourly(script, app):
    seen = {}

    def fake_run(entries, **kwargs):
        seen["entries"], seen["kwargs"] = entries, kwargs

    assert script.main(["--every", "5"], run=fake_run) == 0
    sweep, prune = seen["entries"]
    assert all(isinstance(e, Every) for e in seen["entries"])
    assert (sweep.name, sweep.seconds, prune.name, prune.seconds) == ("sweep", 5.0, "prune", 3600.0)
    assert seen["kwargs"]["on_result"] is script.print_result


def test_the_real_runner_runs_both_entries_then_stops_when_asked(client, app, h, script, capsys):
    task = timed(client, h)
    stop, ran = threading.Event(), []

    def on_result(entry, result, error):
        assert error is None
        ran.append(entry.name)
        script.print_result(entry, result, error)
        if {"sweep", "prune"} <= set(ran):
            stop.set()

    entries = script.entries(app.state.session_factory, app.state.settings, None, 60.0)
    run_schedule(entries, stop=stop, install_signals=False, on_result=on_result)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {"sweep", "prune"} <= set(ran) and len(lines) == 2
    assert any("sweep" in line for line in lines) and any("prune" in line for line in lines)
    assert notices_of(app, task["id"]) == []  # the fixture clock (2026-11-08) is before the task is due


def test_the_script_configures_logging_for_the_loop(script, app, monkeypatch):
    calls = []
    monkeypatch.setattr(script.logging, "basicConfig", lambda **kw: calls.append(kw))
    script.main(["--every", "5"], run=lambda *a, **k: None)
    assert calls and calls[0]["level"] == script.logging.INFO


def test_every_below_one_second_is_refused(script):
    with pytest.raises(SystemExit):
        script.main(["--every", "0.5"])


def test_grandfather_before_reaches_the_sweep_through_the_script(client, app, h, script, capsys, monkeypatch):
    old = timed(client, h, title="Old", day="2026-11-09", at="10:00")
    monkeypatch.setenv("SDK_EXAMPLE_GRANDFATHER_BEFORE", "2026-11-10T00:00:00Z")
    assert script.main(["--once", "--now", "2026-11-09T10:05:00Z"]) == 0
    assert json.loads(capsys.readouterr().out)["sweep"]["claimed"] == 0
    assert notices_of(app, old["id"]) == []
