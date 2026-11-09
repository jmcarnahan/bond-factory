import threading
from datetime import UTC, date, datetime

from conftest import (
    NOW,
    Base,
    EtagMismatch,
    FakeMirror,
    FakeProviders,
    NotFound,
    ReconnectRequired,
    Task,
    Unavailable,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bond_tasks_py import (
    MirrorPointer,
    TaskCreate,
    TaskUpdate,
    classify,
    mark_mirror,
    mirror_eligible,
    remove_event,
    service,
    sync_mirror,
)

DAY = date(2026, 11, 10)


def make(session, owner="u1", **fields):
    task = service.create(session, task_model=Task, owner_user_id=owner, actor_user_id=owner,
                          data=TaskCreate(title="Send docs", **{"due_date": DAY, **fields}), now=NOW)
    session.commit()
    return task


def edit(session, task, actor="u1", **fields):
    service.update(session, task=task, actor_user_id=actor, data=TaskUpdate.model_validate(fields), now=NOW)
    session.commit()


def run(factory, task, providers, tz="UTC"):
    sync_mirror(factory, Task, task.id, providers, tz=tz)


def row(factory, task_id):
    with factory() as s:
        return s.get(Task, task_id)


def setup_pair():
    g, m = FakeMirror(), FakeMirror()
    return g, m, FakeProviders(u1=("google", g), u2=("microsoft", m))


def test_eligibility_rule(session):
    task = make(session)
    assert mirror_eligible(task)
    task.mirror_enabled = False
    assert not mirror_eligible(task)
    task.mirror_enabled, task.status = True, "done"
    assert not mirror_eligible(task)
    task.status, task.due_date = "open", None
    assert not mirror_eligible(task)


def test_mark_mirror_values(session):
    task = make(session)
    task.status = "done"
    mark_mirror(task)
    assert task.mirror_status == "skipped"
    task.status = "open"
    mark_mirror(task)
    assert task.mirror_status == "pending"


def test_create_records_provider_event_etag_and_mailbox(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    fresh = row(factory, task.id)
    assert (fresh.mirror_status, fresh.external_provider, fresh.external_event_id) == ("mirrored", "google", "ev-1")
    assert (fresh.external_account_user_id, fresh.external_etag) == ("u1", 'W/"1"')
    assert g.events["ev-1"]["subject"] == "Send docs"


def test_timed_task_becomes_a_half_hour_event_in_utc(factory, session):
    g, _, providers = setup_pair()
    task = make(session, due_time="09:00")
    run(factory, task, providers, tz="America/Los_Angeles")
    event = g.events["ev-1"]
    assert event["start"] == datetime(2026, 11, 10, 17, 0, tzinfo=UTC)
    assert (event["end"] - event["start"]).seconds == 1800 and event["is_all_day"] is False


def test_date_only_task_is_an_all_day_event(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    event = g.events["ev-1"]
    assert event["is_all_day"] is True and event["start"] == datetime(2026, 11, 10, tzinfo=UTC)


def test_update_sends_the_stored_etag(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    edit(session, task, title="Renamed")
    run(factory, task, providers)
    update = next(c for c in g.calls if c[0] == "update")
    assert update[1] == "ev-1" and update[3] == 'W/"1"' and update[2]["subject"] == "Renamed"
    fresh = row(factory, task.id)
    assert fresh.external_etag == 'W/"2"' and g.events["ev-1"]["subject"] == "Renamed"


def test_stale_etag_rereads_then_updates(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    g.etags["ev-1"] = 7  # someone edited it in the calendar
    edit(session, task, title="Again")
    run(factory, task, providers)
    assert [c[0] for c in g.calls] == ["create", "update", "get", "update"]
    fresh = row(factory, task.id)
    assert fresh.mirror_status == "mirrored" and fresh.external_etag == 'W/"8"'


def test_event_deleted_in_the_calendar_is_recreated(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    del g.events["ev-1"]
    edit(session, task, title="Again")
    run(factory, task, providers)
    assert row(factory, task.id).external_event_id == "ev-2"


def test_completing_deletes_the_event_and_clears_the_pointer(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    service.complete(session, task, "u1", NOW)
    session.commit()
    run(factory, task, providers)
    fresh = row(factory, task.id)
    assert g.events == {} and fresh.external_event_id is None and fresh.mirror_status == "skipped"
    assert fresh.external_etag is None and fresh.external_provider is None


def test_reassign_deletes_in_the_old_mailbox_and_creates_in_the_new(factory, session):
    g, m, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    edit(session, task, assigned_user_id="u2")
    run(factory, task, providers)
    fresh = row(factory, task.id)
    assert g.events == {} and list(m.events) == ["ev-1"]
    assert (fresh.external_provider, fresh.external_account_user_id) == ("microsoft", "u2")


def test_no_connection_is_skipped(factory, session):
    task = make(session)
    run(factory, task, FakeProviders())
    assert row(factory, task.id).mirror_status == "skipped"


def test_provider_refusal_is_failed_and_next_sync_retries(factory, session):
    g, _, providers = setup_pair()
    g.fail["create_event"] = [Unavailable()]
    task = make(session)
    run(factory, task, providers)
    assert row(factory, task.id).mirror_status == "failed"
    run(factory, task, providers)
    assert row(factory, task.id).mirror_status == "mirrored"


def test_a_connection_that_needs_reconnecting_is_skipped(factory, session):
    g, _, providers = setup_pair()
    g.fail["create_event"] = [ReconnectRequired()]
    task = make(session)
    run(factory, task, providers)
    assert row(factory, task.id).mirror_status == "skipped"


def test_sync_never_raises_even_when_the_lookup_explodes(factory, session):
    class Broken:
        def for_user(self, session, user_id):
            raise RuntimeError("db down")

    task = make(session)
    run(factory, task, Broken())  # no exception
    assert row(factory, task.id).mirror_status == "pending"


def test_sync_of_a_missing_task_is_a_noop(factory):
    sync_mirror(factory, Task, "gone", FakeProviders())


def test_failed_delete_keeps_the_pointer_for_a_retry(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    service.cancel(session, task, "u1", NOW)
    session.commit()
    g.fail["delete_event"] = [Unavailable()]
    run(factory, task, providers)
    assert row(factory, task.id).external_event_id == "ev-1" and row(factory, task.id).mirror_status == "failed"
    run(factory, task, providers)
    assert row(factory, task.id).external_event_id is None and g.events == {}


def test_unreachable_old_mailbox_drops_the_pointer(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    g.fail["delete_event"] = [ReconnectRequired()]
    edit(session, task, assigned_user_id="u2")
    run(factory, task, providers)
    assert row(factory, task.id).external_account_user_id == "u2"


def test_task_deleted_while_the_provider_answered_leaves_no_stray_event(factory, session):
    task = make(session)

    class Racy(FakeMirror):
        def create_event(self, draft):
            result = super().create_event(draft)
            with factory() as other:
                other.delete(other.get(Task, task.id))
                other.commit()
            return result

    racy = Racy()
    sync_mirror(factory, Task, task.id, FakeProviders(u1=("google", racy)))
    assert racy.events == {}


def test_completed_while_the_provider_answered_undoes_the_event(factory, session):
    task = make(session)

    class Racy(FakeMirror):
        def create_event(self, draft):
            result = super().create_event(draft)
            with factory() as other:
                t = other.get(Task, task.id)
                t.status = "done"
                other.commit()
            return result

    racy = Racy()
    sync_mirror(factory, Task, task.id, FakeProviders(u1=("google", racy)))
    fresh = row(factory, task.id)
    assert racy.events == {} and fresh.external_event_id is None and fresh.mirror_status == "skipped"


def test_remove_event_after_a_hard_delete(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    session.refresh(task)
    pointer = service.delete(session, task, "u1")
    assert pointer == MirrorPointer("u1", "google", "ev-1")
    remove_event(factory, providers, pointer)
    assert g.events == {}


def test_remove_event_tolerates_missing_and_failing(factory):
    g = FakeMirror()
    providers = FakeProviders(u1=("google", g))
    remove_event(factory, providers, MirrorPointer("u1", "google", "nope"))
    g.fail["delete_event"] = [Unavailable()]
    remove_event(factory, providers, MirrorPointer("u1", "google", "nope"))
    remove_event(factory, FakeProviders(), MirrorPointer("u9", None, "x"))


def test_error_classification_by_class_name_or_status():
    assert classify(NotFound()) == "not_found" and classify(EtagMismatch()) == "etag"
    assert classify(ReconnectRequired()) == "reconnect" and classify(Unavailable()) == "other"

    class Gone(Exception):
        status = 410

    class Stale(Exception):
        status = 412

    assert classify(Gone()) == "not_found" and classify(Stale()) == "etag"


def test_two_quick_syncs_leave_exactly_one_event(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/mirror.db", connect_args={"timeout": 15})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        task = make(setup)
    barrier = threading.Barrier(2, timeout=10)

    class Slow(FakeMirror):
        def create_event(self, draft):
            result = super().create_event(draft)
            barrier.wait()  # both passes have created their event before either records it
            return result

    shared = Slow()
    providers = FakeProviders(u1=("google", shared))
    threads = [threading.Thread(target=run, args=(factory, task, providers)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    fresh = row(factory, task.id)
    assert len(shared.events) == 1 and list(shared.events) == [fresh.external_event_id]
    assert fresh.mirror_status == "mirrored"
