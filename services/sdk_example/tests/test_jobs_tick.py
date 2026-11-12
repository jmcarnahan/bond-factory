"""POST /jobs/tick: fake-mode time travel for the sweep and the job queue."""

from datetime import UTC, datetime, timedelta

from connections_util import headers

from sdk_example.models.jobs import BackgroundJob


def make_task(client, h, due_time):
    reply = client.post("/tasks", json={"title": f"at {due_time}", "due_date": "2026-11-08", "due_time": due_time,
                                        "time_zone": "UTC"}, headers=h)
    assert reply.status_code == 201
    return reply.json()


def test_needs_a_session(client):
    assert client.post("/jobs/tick", json={}).status_code == 401


def test_the_tick_runs_the_sweep_as_of_now(client):
    h = headers(client)
    make_task(client, h, "10:00")
    make_task(client, h, "12:00")
    first = client.post("/jobs/tick", json={"now": "2026-11-08T10:30:00Z"}, headers=h).json()
    # only the 10:00 task is due: past its 15-minute due window. The 12:00 task's close stage starts at 11:00.
    assert first["sweep"] == {"claimed": 1, "skipped": 0, "queued": 1, "repaired": 0, "errors": 0}  # queued: its push row
    [notice] = client.get("/notices", headers=h).json()["items"]
    assert notice["data"]["stage"] == "past" and "at 10:00" in notice["title"]
    again = client.post("/jobs/tick", json={"now": "2026-11-08T10:30:00Z"}, headers=h).json()
    assert again["sweep"]["claimed"] == 0  # the same instant claims nothing new
    noon = client.post("/jobs/tick", json={"now": "2026-11-08T11:30:00Z"}, headers=h).json()
    assert noon["sweep"]["claimed"] == 1  # now the 12:00 task is in its close stage
    stages = {n["title"]: n["data"]["stage"] for n in client.get("/notices", headers=h).json()["items"]}
    assert sorted(stages.values()) == ["close", "past"]


def test_the_tick_still_runs_due_jobs(client):
    h = headers(client)
    body = client.post("/jobs/tick", json={"now": "2026-11-08T10:30:00Z"}, headers=h).json()
    assert [r["job_type"] for r in body["ran"]] == []  # only the daily prune job is queued, due at midnight
    later = client.post("/jobs/tick", json={"now": "2026-11-09T00:30:00Z"}, headers=h).json()
    row = next(r for r in later["ran"] if r["job_type"] == "signin_prune")
    assert {"id", "job_type", "key", "status", "error", "summary", "skipped"} <= set(row)
    assert row["status"] == "done" and row["error"] is None


def test_the_clock_is_released_after_the_pass(client, app):
    h = headers(client)
    client.post("/jobs/tick", json={"now": "2026-11-08T10:00:00Z"}, headers=h)
    assert app.state.clock.frozen is False


def test_without_now_it_uses_real_time(client, app):
    h = headers(client)
    app.state.clock.unfreeze()  # the fixture pins 2026-11-08; with nothing pinned a bare tick reads real time
    just_now = datetime.now(UTC) - timedelta(minutes=1)  # due a minute ago: inside its 15-minute due window
    task = client.post("/tasks", json={"title": "Now", "due_date": just_now.date().isoformat(),
                                       "due_time": just_now.strftime("%H:%M"), "time_zone": "UTC"}, headers=h).json()
    reply = client.post("/jobs/tick", json={}, headers=h)
    assert reply.status_code == 200 and set(reply.json()) == {"ran", "sweep", "deliver"}
    assert reply.json()["sweep"]["claimed"] == 1  # the sweep ran at the real time, not the fixture's 2026-11-08
    [notice] = client.get("/notices", headers=h).json()["items"]
    assert notice["data"]["task_id"] == task["id"] and notice["data"]["stage"] == "due"
    assert app.state.clock.frozen is False
    with app.state.session_factory() as session:
        assert session.query(BackgroundJob).filter_by(job_type="task_reminder").count() == 0


def test_bad_now_is_a_422(client):
    reply = client.post("/jobs/tick", json={"now": "tomorrow-ish"}, headers=headers(client))
    assert reply.status_code == 422 and reply.json()["detail"]["code"] == "invalid_now"


def test_a_naive_now_is_read_as_utc(client):
    h = headers(client)
    make_task(client, h, "10:00")
    body = client.post("/jobs/tick", json={"now": "2026-11-08T10:30:00"}, headers=h).json()
    assert body["sweep"]["claimed"] >= 1


def test_real_mode_has_no_tick(client, app):
    h = headers(client)
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.post("/jobs/tick", json={}, headers=h).status_code == 404
