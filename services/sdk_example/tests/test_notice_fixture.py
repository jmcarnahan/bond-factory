"""The example's inbox ids equal the shared fixture's (fixtures/tasks/notice_ids.json), so a change to the id formula is
caught here as well as in the libraries.

The fixture's users are "user-1" (owner) and "user-2" (assignee) and its task id is "task-0001", none of which the
routes can mint (ids come from the server, users from the seeded set). So the test inserts the two users, creates the
task through the lib's own `create` with the fixture's ids, and then lets the real sweep (POST /jobs/tick) and the
inbox store do the rest. The token 29537310 is epoch minutes: due 2026-02-28 00:30 UTC.
"""

import json
from pathlib import Path

import bond_tasks_py as tasks
from connections_util import headers
from todo_util import notices_of

from sdk_example.models.auth import User
from sdk_example.models.tasks import Task

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "tasks" / "notice_ids.json"
CASES = [c for c in json.loads(FIXTURE.read_text()) if c["task_id"] == "task-0001"]


def add_fixture_task(app) -> None:
    with app.state.session_factory() as session:
        for number in (1, 2):
            session.add(User(id=f"user-{number}", email=f"fixture-{number}@example.com", name=f"Fixture {number}",
                             capabilities=["tasks.write"]))
        session.flush()
        tasks.create(
            session, task_model=Task, owner_user_id="user-1", actor_user_id="user-1", now=app.state.clock.utcnow_naive(),
            tz="UTC", user_exists=lambda user_id: user_id in ("user-1", "user-2"),
            data=tasks.TaskCreate(id="task-0001", title="Fixture task", due_date="2026-02-28", due_time="00:30",
                                  assigned_user_id="user-2", time_zone="UTC"))
        session.commit()


def test_the_inbox_holds_the_fixtures_notice_ids(client, app):
    assert {(c["user_id"], c["stage"], c["seq"]) for c in CASES} == {
        ("user-2", "close", 0), ("user-2", "due", 0), ("user-1", "past", 0), ("user-2", "past", 5)}
    add_fixture_task(app)
    h = headers(client)
    for instant in ("2026-02-27T23:45:00Z",   # close, for the assignee
                    "2026-02-28T00:35:00Z",   # due
                    "2026-02-28T08:30:00Z",   # past seq 0 (its 00:45 slot was in quiet hours), owner and assignee
                    "2026-03-05T08:30:00Z"):  # past seq 5, the fifth morning
        assert client.post("/jobs/tick", json={"now": instant}, headers=h).json()["sweep"]["errors"] == 0
    stored = {n.id: (n.user_id, n.data["stage"], n.data["seq"]) for n in notices_of(app, "task-0001")}
    for case in CASES:
        assert stored.get(case["notice_id"]) == (case["user_id"], case["stage"], case["seq"]), case
    assert tasks.deadline_token(_task(app)) == "29537310"


def _task(app):
    with app.state.session_factory() as session:
        return session.get(Task, "task-0001")
