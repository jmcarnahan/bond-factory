from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_tasks_py import TasksMixin
from bond_tasks_py.protocols import MirrorDraft

NOW = datetime(2026, 11, 8, 12, 0, 0)  # naive UTC
Base = declarative_base()


class Task(TasksMixin, Base):
    pass


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(factory):
    with factory() as s:
        yield s


class NotFound(Exception):
    status = 404


class EtagMismatch(Exception):
    status = 412


class ReconnectRequired(Exception):
    status = 401


class Unavailable(Exception):
    status = 503


class FakeScheduler:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.cancelled: list[str] = []

    def enqueue(self, session, *, job_type, payload, run_at, dedupe_key):
        self.jobs[dedupe_key] = {"job_type": job_type, "payload": payload, "run_at": run_at}

    def cancel(self, session, *, dedupe_key):
        self.cancelled.append(dedupe_key)
        self.jobs.pop(dedupe_key, None)


class FakeMirror:
    def __init__(self):
        self.events: dict[str, dict] = {}
        self.etags: dict[str, int] = {}
        self.calls: list[tuple] = []
        self.fail: dict[str, list[Exception]] = {}  # method name -> exceptions to raise, one per call
        self.counter = 0

    def _maybe_fail(self, name):
        queue = self.fail.get(name)
        if queue:
            raise queue.pop(0)

    def _event(self, event_id):
        class Event:
            id = event_id
            etag = f'W/"{self.etags[event_id]}"'

        return Event()

    def create_event(self, draft: MirrorDraft):
        self.calls.append(("create", draft))
        self._maybe_fail("create_event")
        self.counter += 1
        event_id = f"ev-{self.counter}"
        self.events[event_id] = {"subject": draft.subject, "start": draft.start, "end": draft.end,
                                 "is_all_day": draft.is_all_day}
        self.etags[event_id] = 1
        return self._event(event_id)

    def update_event(self, event_id, patch, *, etag=None):
        self.calls.append(("update", event_id, patch, etag))
        self._maybe_fail("update_event")
        if event_id not in self.events:
            raise NotFound()
        if etag is not None and etag != f'W/"{self.etags[event_id]}"':
            raise EtagMismatch()
        self.events[event_id].update(patch)
        self.etags[event_id] += 1
        return self._event(event_id)

    def get_event(self, event_id):
        self.calls.append(("get", event_id))
        self._maybe_fail("get_event")
        if event_id not in self.events:
            raise NotFound()
        return self._event(event_id)

    def delete_event(self, event_id):
        self.calls.append(("delete", event_id))
        self._maybe_fail("delete_event")
        if event_id not in self.events:
            raise NotFound()
        del self.events[event_id]


class FakeProviders:
    def __init__(self, **by_user):
        self.by_user = by_user  # user id -> (provider name, FakeMirror)

    def for_user(self, session, user_id):
        return self.by_user.get(user_id)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)
