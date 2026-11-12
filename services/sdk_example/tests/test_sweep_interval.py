"""The two ways to run the sweep for real: scripts/sweep_interval.py and the jobs tick `before` hook."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import bond_jobs
import pytest
from connections_util import headers
from todo_util import inbox, notices_of, sweep, timed

from sdk_example import sweep_wiring
from sdk_example.signin_prune import schedule as schedule_prune

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sweep_interval.py"


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("sweep_interval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def h(client):
    return headers(client)


def test_once_with_now_claims_what_is_due_and_prints_one_json_line(client, app, h, script, capsys):
    task = timed(client, h)
    assert script.main(["--once", "--now", "2026-11-09T10:05:00Z"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["at"] == "2026-11-09T10:05:00Z" and report["sweep"]["claimed"] == 1
    assert report["deliver"] == {} and set(report["prune"]) == {"ledger", "notices"}  # no push key: inbox only
    assert [n.data["stage"] for n in notices_of(app, task["id"])] == ["due"]
    assert len(inbox(client, h)) == 1


def test_a_second_pass_at_the_same_instant_claims_nothing(client, app, h, script, capsys):
    timed(client, h)
    script.main(["--once", "--now", "2026-11-09T10:05:00Z"])
    capsys.readouterr()
    script.main(["--once", "--now", "2026-11-09T10:05:00+00:00"])
    assert json.loads(capsys.readouterr().out)["sweep"]["claimed"] == 0


def test_the_script_and_the_tick_route_never_double_a_notice(client, app, h, script):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T10:05:00Z")
    script.main(["--once", "--now", "2026-11-09T10:05:00Z"])
    script.main(["--once", "--now", "2026-11-09T10:10:00Z"])
    assert len(notices_of(app, task["id"])) == 1


def test_a_naive_now_is_read_as_utc_and_now_needs_once(script, capsys):
    assert script.parse_now("2026-11-09T10:05:00").isoformat() == "2026-11-09T10:05:00"
    assert script.parse_now("2026-11-09T05:05:00-05:00").isoformat() == "2026-11-09T10:05:00"
    with pytest.raises(SystemExit):
        script.main(["--now", "2026-11-09T10:05:00Z"])


def test_prune_forgets_a_closed_tasks_old_rows(client, app, h, script, capsys):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T10:05:00Z")
    client.post(f"/tasks/{task['id']}/complete", headers=h)
    script.main(["--once", "--now", "2027-01-20T00:00:00Z"])  # far past the retention window
    assert json.loads(capsys.readouterr().out)["prune"]["notices"] >= 1
    assert notices_of(app, task["id"]) == []


def test_the_worker_loop_hook_does_the_same_as_the_tick_route(client, app, h):
    task = timed(client, h)
    app.state.clock.freeze(datetime(2026, 11, 9, 10, 5, tzinfo=UTC))
    hook = sweep_wiring.before_hook(app, schedule_prune)
    bond_jobs.tick(app.state.engine, app.state.session_factory, app.state.job_registry, app.state.clock,
                   before=hook, before_every=sweep_wiring.BEFORE_EVERY)
    assert [n.data["stage"] for n in notices_of(app, task["id"])] == ["due"]
    again = bond_jobs.tick(app.state.engine, app.state.session_factory, app.state.job_registry, app.state.clock,
                           before=hook, before_every=sweep_wiring.BEFORE_EVERY)  # throttled: the hook is skipped
    assert again == [] and len(notices_of(app, task["id"])) == 1
