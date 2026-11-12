"""Helpers for the TODO checklist tests: timed tasks, ticks, the inbox, the mock phone, notice ids."""

from bond_tasks_py import deadline_token, notice_id

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID, User
from sdk_example.models.notices import Notice
from sdk_example.models.tasks import Task


def grant_write(app, user_id=VIEWER_USER_ID):
    with app.state.session_factory() as session:
        session.get(User, user_id).capabilities = ["tasks.write"]
        session.commit()


def timed(client, h, title="Ring", day="2026-11-09", at="10:00", zone="UTC", **extra) -> dict:
    """A task due at a clock time on a day in `zone`."""
    reply = client.post("/tasks", json={"title": title, "due_date": day, "due_time": at, "time_zone": zone, **extra},
                        headers=h)
    assert reply.status_code == 201, reply.text
    return reply.json()


def sweep(client, h, now) -> dict:
    reply = client.post("/jobs/tick", json={"now": now}, headers=h)
    assert reply.status_code == 200, reply.text
    return reply.json()


def inbox(client, h, **params) -> list[dict]:
    reply = client.get("/notices", params={"limit": 200, **params}, headers=h)
    assert reply.status_code == 200, reply.text
    return reply.json()["items"]


def notices_of(app, task_id: str) -> list[Notice]:
    """Every stored notice of a task, dismissed or not, oldest first."""
    with app.state.session_factory() as session:
        return session.query(Notice).filter_by(source_id=task_id).order_by(Notice.created_at, Notice.id).all()


def expected_id(app, task_id: str, stage: str, seq: int = 0, user_id: str = DEMO_USER_ID) -> str:
    with app.state.session_factory() as session:
        return notice_id(task_id, user_id, stage, seq, deadline_token(session.get(Task, task_id)))


def register_phone(client, h, token="tok-demo-1", device_id="dev-1") -> None:
    reply = client.post("/push/devices", json={"device_id": device_id, "token": token, "platform": "ios",
                                               "environment": "sandbox", "topic": "org.example.app"}, headers=h)
    assert reply.status_code == 201, reply.text


def pushed(client, h, task_id: str | None = None) -> list[dict]:
    items = client.get("/fake/push/sent", headers=h).json()["items"]
    return [m for m in items if task_id is None or m["data"].get("task_id") == task_id]
