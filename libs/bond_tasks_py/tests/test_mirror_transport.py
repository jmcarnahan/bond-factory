"""Transport failures (no answer from the provider) with and without ``transport_pending``."""

import logging
from datetime import date

import pytest
from conftest import (
    NOW,
    EtagMismatch,
    FakeMirror,
    FakeProviders,
    NotFound,
    ReconnectRequired,
    Task,
    Unavailable,
)

from bond_tasks_py import TaskCreate, TaskUpdate, classify, service, sync_mirror
from bond_tasks_py.mirror import TRANSPORT_NAMES

DAY = date(2026, 11, 10)


class Down(Exception):
    """A provider error shaped like bond_calendar.Unavailable(status=0)."""

    status = 0


class ConnectError(Exception):
    pass


class TimeoutException(Exception):
    status = 503


def make(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="Send docs", due_date=DAY), now=NOW)
    session.commit()
    return task


def edit(session, task, **fields):
    service.update(session, task=task, actor_user_id="u1", data=TaskUpdate.model_validate(fields), now=NOW)
    session.commit()


def row(factory, task_id):
    with factory() as s:
        return s.get(Task, task_id)


def run(factory, task, mirror, flag):
    sync_mirror(factory, Task, task.id, FakeProviders(u1=("google", mirror)), transport_pending=flag)


def pointer(t):
    return (t.external_event_id, t.external_account_user_id, t.external_provider, t.external_etag)


def test_case1_create_transport_error_stays_pending(factory, session, caplog):
    m = FakeMirror()
    m.fail["create_event"] = [Down()]
    task = make(session)
    with caplog.at_level(logging.WARNING):
        run(factory, task, m, True)
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "pending" and pointer(fresh) == (None, None, None, None) and not m.events
    assert "did not answer" in caplog.text and "next edit retries" in caplog.text


def test_case2_next_edit_creates_exactly_one_event(factory, session):
    m = FakeMirror()
    m.fail["create_event"] = [Down()]
    task = make(session)
    run(factory, task, m, True)
    assert [c[0] for c in m.calls] == ["create"] and not m.events  # one failed call, nothing stored
    edit(session, task, title="Again")
    run(factory, task, m, True)
    fresh = row(factory, task.id)
    assert [c[0] for c in m.calls] == ["create", "create"] and len(m.events) == 1
    assert fresh.mirror_status == "mirrored" and pointer(fresh) == ("ev-1", "u1", "google", 'W/"1"')


def test_case3_update_transport_error_keeps_pointer_and_is_pending(factory, session):
    m = FakeMirror()
    task = make(session)
    run(factory, task, m, True)
    before = pointer(row(factory, task.id))
    m.fail["update_event"] = [Down()]
    edit(session, task, title="Renamed")
    run(factory, task, m, True)
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "pending" and pointer(fresh) == before and before[0] == "ev-1"
    assert fresh.title == "Renamed" and len(m.events) == 1


def test_case4_provider_5xx_is_failed(factory, session):
    m = FakeMirror()
    m.fail["create_event"] = [Unavailable()]
    task = make(session)
    run(factory, task, m, True)
    assert row(factory, task.id).mirror_status == "failed"


def test_case5_reconnect_is_skipped(factory, session):
    m = FakeMirror()
    m.fail["create_event"] = [ReconnectRequired()]
    task = make(session)
    run(factory, task, m, True)
    assert row(factory, task.id).mirror_status == "skipped"


@pytest.mark.parametrize("exc", [Down(), ConnectError(), ConnectionRefusedError(), TimeoutError()])
def test_default_still_ends_failed(factory, session, exc):
    m = FakeMirror()
    m.fail["create_event"] = [exc]
    task = make(session)
    run(factory, task, m, False)
    assert row(factory, task.id).mirror_status == "failed"
    m.fail["create_event"] = [exc]
    sync_mirror(factory, Task, task.id, FakeProviders(u1=("google", m)))  # omitted flag = default
    assert row(factory, task.id).mirror_status == "failed"


def test_etag_reread_transport_failure_keeps_pointer_pending(factory, session):
    m = FakeMirror()
    task = make(session)
    run(factory, task, m, True)
    before = pointer(row(factory, task.id))
    m.etags["ev-1"] += 1  # provider-side edit: the stored etag is stale
    m.fail["get_event"] = [Down()]
    edit(session, task, title="Renamed")
    run(factory, task, m, True)
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "pending" and pointer(fresh) == before
    assert [c[0] for c in m.calls][-2:] == ["update", "get"]


def test_etag_reread_transport_failure_default_is_failed(factory, session):
    m = FakeMirror()
    task = make(session)
    run(factory, task, m, False)
    m.etags["ev-1"] += 1
    m.fail["get_event"] = [Down()]
    edit(session, task, title="Renamed")
    run(factory, task, m, False)
    assert row(factory, task.id).mirror_status == "failed"


def test_classify_transport_kinds():
    assert classify(Down()) == "transport"
    assert classify(ConnectError()) == "transport"
    assert classify(ConnectionRefusedError()) == "transport"
    assert classify(TimeoutError()) == "transport"
    assert classify(TimeoutException()) == "other"  # status 503: the provider answered


def test_classify_precedence_and_non_transport_statuses():
    assert classify(NotFound()) == "not_found" and classify(EtagMismatch()) == "etag"
    assert classify(ReconnectRequired()) == "reconnect" and classify(Unavailable()) == "other"

    class Odd(Exception):
        pass

    for value in (False, None):
        e = Odd()
        e.status = value
        assert classify(e) == "other"
    assert classify(Odd()) == "other"

    class Gone(Down):
        status = 404

    assert classify(Gone()) == "not_found"


def test_transport_names_constant():
    assert {"TransportError", "ConnectError", "TimeoutException", "ConnectionError", "TimeoutError"} == TRANSPORT_NAMES


def test_task_completed_while_the_provider_is_silent_keeps_the_newer_state(factory, session):
    class Completing(FakeMirror):
        def create_event(self, draft):
            with factory() as s:  # the completing write lands while the provider call hangs
                t = s.get(Task, task.id)
                t.status, t.mirror_status = "done", "skipped"
                s.commit()
            raise Down()

    m = Completing()
    task = make(session)
    run(factory, task, m, True)
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "skipped" and pointer(fresh) == (None, None, None, None)


@pytest.mark.parametrize("flag", [True, False])
@pytest.mark.parametrize("how", ["mirror_off", "completed"])
def test_delete_path_is_unchanged_by_the_flag(factory, session, flag, how):
    m = FakeMirror()
    task = make(session)
    run(factory, task, m, flag)
    before = pointer(row(factory, task.id))
    assert before[0] == "ev-1"
    if how == "mirror_off":
        edit(session, task, mirror_enabled=False)
    else:
        service.complete(session, task=task, actor_user_id="u1", now=NOW)
        session.commit()
    m.fail["delete_event"] = [Down()]
    run(factory, task, m, flag)
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "failed" and pointer(fresh) == before


def test_a_concurrent_pass_that_already_mirrored_is_not_overwritten_with_pending(factory, session):
    class Racing(FakeMirror):
        def update_event(self, event_id, patch, *, etag=None):
            with factory() as s:  # a faster pass records its result while this one waits on the provider
                t = s.get(Task, task.id)
                t.mirror_status, t.external_etag = "mirrored", 'W/"9"'
                s.commit()
            raise Down()

    m = Racing()
    task = make(session)
    run(factory, task, m, True)
    session.refresh(task)  # the sync ran in other sessions
    edit(session, task, title="Renamed")  # pending again, pointer kept
    assert row(factory, task.id).mirror_status == "pending"
    run(factory, task, m, True)
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "mirrored" and fresh.external_etag == 'W/"9"' and fresh.external_event_id == "ev-1"
