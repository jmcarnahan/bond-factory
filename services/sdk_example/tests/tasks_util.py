"""Helpers shared by the tasks route tests."""

from datetime import UTC, datetime

from sdk_example.models.auth import VIEWER_USER_ID, User

T0 = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
TODAY = "2026-11-08"


def grant(app, user_id=VIEWER_USER_ID, *caps):
    """Give a seeded user capabilities (default: tasks.write)."""
    with app.state.session_factory() as session:
        session.get(User, user_id).capabilities = list(caps or ["tasks.write"])
        session.commit()


def make(client, h, **body):
    # ``today`` pinned to TODAY so ``overdue`` does not depend on the wall-clock date the suite runs on.
    reply = client.post("/tasks", json={"title": "Call back", **body}, headers=h, params={"today": TODAY})
    assert reply.status_code == 201, reply.text
    return reply.json()


def code(reply) -> str:
    return reply.json()["detail"]["code"]


def tick(client, h, now):
    reply = client.post("/jobs/tick", json={"now": now}, headers=h)
    assert reply.status_code == 200, reply.text
    return reply.json()["ran"]
