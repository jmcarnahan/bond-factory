"""POST /jobs/tick: fake-mode time travel for the job queue."""

from connections_util import headers

from sdk_example.models.jobs import BackgroundJob


def make_task(client, h, due_time):
    reply = client.post("/tasks", json={"title": f"at {due_time}", "due_date": "2026-11-08", "due_time": due_time,
                                        "remind_minutes_before": 0}, headers=h)
    assert reply.status_code == 201
    return reply.json()


def test_needs_a_session(client):
    assert client.post("/jobs/tick", json={}).status_code == 401


def test_runs_only_what_is_due_as_of_now(client):
    h = headers(client)
    make_task(client, h, "10:00")
    make_task(client, h, "12:00")
    first = client.post("/jobs/tick", json={"now": "2026-11-08T10:30:00Z"}, headers=h).json()["ran"]
    assert [r["job_type"] for r in first] == ["task_reminder"] and first[0]["status"] == "done"
    second = client.post("/jobs/tick", json={"now": "2026-11-08T13:00:00Z"}, headers=h).json()["ran"]
    assert len(second) == 1 and second[0]["id"] != first[0]["id"]


def test_result_rows_carry_the_runner_fields(client):
    h = headers(client)
    make_task(client, h, "10:00")
    row = client.post("/jobs/tick", json={"now": "2026-11-08T10:00:00Z"}, headers=h).json()["ran"][0]
    assert {"id", "job_type", "key", "status", "error", "summary", "skipped"} <= set(row)
    assert row["summary"] == "reminded" and row["error"] is None


def test_the_clock_is_released_after_the_pass(client, app):
    h = headers(client)
    client.post("/jobs/tick", json={"now": "2026-11-08T10:00:00Z"}, headers=h)
    assert app.state.clock.frozen is False


def test_without_now_it_uses_real_time_and_old_jobs_run(client, app):
    h = headers(client)
    make_task(client, h, "10:00")  # 2026-11-08 is not in the past of the real clock when the suite runs later
    ran = client.post("/jobs/tick", json={}, headers=h).json()["ran"]
    with app.state.session_factory() as session:
        pending = session.query(BackgroundJob).filter_by(status="pending").count()
    assert len(ran) + pending == 1


def test_bad_now_is_a_422(client):
    reply = client.post("/jobs/tick", json={"now": "tomorrow-ish"}, headers=headers(client))
    assert reply.status_code == 422 and reply.json()["detail"]["code"] == "invalid_now"


def test_a_naive_now_is_read_as_utc(client):
    h = headers(client)
    make_task(client, h, "10:00")
    assert len(client.post("/jobs/tick", json={"now": "2026-11-08T10:30:00"}, headers=h).json()["ran"]) == 1


def test_real_mode_has_no_tick(client, app):
    h = headers(client)
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.post("/jobs/tick", json={}, headers=h).status_code == 404
