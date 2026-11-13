from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from legacy_host.app import create_app
from legacy_host.models import Case, Client, User

TEST_NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
USERS = {"u-owner": "Olive Owner", "u-editor": "Eddie Editor", "u-admin": "Ada Admin", "u-stranger": "Sam Stranger"}


def seed(app) -> None:
    with app.state.session_factory() as session:
        for uid, name in USERS.items():
            session.add(User(id=uid, name=name, is_admin=(uid == "u-admin")))
        session.add_all([Client(id="cl-1", name="Acme Test Co"), Client(id="cl-2", name="Other Test Co"),
                         Case(id="ca-1", client_id="cl-1", label="Case One"),
                         Case(id="ca-2", client_id="cl-2", label="Case Two")])
        session.commit()


def as_user(user_id: str) -> dict[str, str]:
    return {"X-User": user_id}


@pytest.fixture
def app(tmp_path):
    """A host on a fresh SQLite file, clock frozen at 2026-11-08 10:00 UTC, four users and two clients seeded."""
    app = create_app(f"sqlite:///{tmp_path}/t.db")
    app.state.clock.freeze(TEST_NOW)
    seed(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def session(app):
    with app.state.session_factory() as s:
        yield s
