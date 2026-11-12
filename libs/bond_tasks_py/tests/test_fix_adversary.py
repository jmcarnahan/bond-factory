"""Fixes after review: at-most-once failed_at, prepare trust rule, draft_for type check."""
from datetime import timedelta

import pytest
from conftest import Ledger, Task
from sqlalchemy import delete
from support_core import HostTask
from test_gaps_sweep_outbox import Probe, run
from test_mirror import make as mirror_make
from test_mirror import row as mirror_row
from test_mirror import setup_pair
from test_outbox import NOW as OUT_NOW
from test_outbox import row, seed
from test_prepare import NOW as PREP_NOW
from test_prepare import Ctx, Op, edit, make

from bond_tasks_py import TaskCreate, TaskError, TaskUpdate, service, sync_mirror, sync_routes


def test_once_channel_ledger_row_gone_is_failed_once(sq_factory):
    with sq_factory() as session:
        seed(session)
        session.execute(delete(Ledger))
        session.commit()
        commits = []
        probe = Probe(commits)
        first = run(session, commits, {"chat": probe}, at_most_once=["chat"])
        assert first.failed == 1 and row(session).failed_at is not None and probe.sent == []
        assert run(session, commits, {"chat": probe}, now=OUT_NOW + timedelta(days=1), at_most_once=["chat"]).leased == 0


def test_once_channel_send_raises_sets_both_stamps(sq_factory):
    with sq_factory() as session:
        seed(session)
        commits = []
        run(session, commits, {"chat": Probe(commits, raises=RuntimeError("x"))}, at_most_once=["chat"])
        got = row(session)
        assert got.delivered_at is not None and got.failed_at is not None and "RuntimeError" in got.last_error


def test_once_channel_failed_verdict_sets_both_stamps(sq_factory):
    with sq_factory() as session:
        seed(session)
        commits = []
        run(session, commits, {"chat": Probe(commits, verdict="failed")}, at_most_once=["chat"])
        got = row(session)
        assert got.delivered_at is not None and got.failed_at is not None


def test_prepare_derived_column_outside_host_columns_is_stored(host_session):
    session = host_session

    def prepare(s, stored, actor, extras):
        return {**extras, "external_ref": "ref"}

    task = service.create(session, task_model=HostTask, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="A"), now=PREP_NOW,
                          host_columns=("contact_id",), prepare=prepare)
    assert task.external_ref == "ref"
    task.external_ref = None
    service.update(session, task=task, actor_user_id="u1", data=TaskUpdate(title="B"), now=PREP_NOW,
                   host_columns=("contact_id",), prepare=prepare)
    assert task.external_ref == "ref"
    route = sync_routes(HostTask, now=lambda: PREP_NOW, host_columns=("contact_id",), prepare=prepare)[("tasks", None)]
    route.handler(session, Ctx("u1"), Op("t1", "put"), {"title": "A"})
    assert session.get(HostTask, "t1").external_ref == "ref"
    session.get(HostTask, "t1").external_ref = None
    route.handler(session, Ctx("u1"), Op("t1", "patch"), {"contact_id": "c"})
    assert session.get(HostTask, "t1").external_ref == "ref"


def test_prepare_never_sees_a_key_outside_host_columns(host_session):
    seen = []

    def prepare(s, stored, actor, extras):
        seen.append(dict(extras))
        return extras

    task = service.create(host_session, task_model=HostTask, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="A"), now=PREP_NOW, host_columns=("contact_id",), prepare=prepare,
                          extras={"contact_id": "c", "external_ref": "smuggled", "loan_id": "l"})
    assert seen == [{"contact_id": "c"}] and task.external_ref is None and task.loan_id is None


def test_prepare_returning_a_lib_column_or_unknown_name_raises(host_session):
    with pytest.raises(ValueError, match="title"):
        make(host_session, prepare=lambda s, t, a, e: {"title": "x"})
    with pytest.raises(ValueError, match="nope"):
        make(host_session, prepare=lambda s, t, a, e: {"nope": 1})
    task = make(host_session)
    with pytest.raises(ValueError, match="status"):
        edit(host_session, task, prepare=lambda s, t, a, e: {"status": "done"})
    assert task.title == "A"


def test_prepare_returning_none_is_a_type_error(host_session):
    with pytest.raises(TypeError, match="mapping"):
        make(host_session, extras={"contact_id": "c"}, prepare=lambda s, t, a, e: None)


def test_prepare_not_called_for_an_actor_without_edit_rights(host_session):
    task = make(host_session)
    calls = []
    with pytest.raises(TaskError):
        edit(host_session, task, actor="stranger", prepare=lambda s, t, a, e: calls.append(1) or e)
    assert calls == []


def test_draft_for_returning_a_non_draft_fails_before_any_provider_call(factory, session):
    g, m, providers = setup_pair()
    task = mirror_make(session)
    sync_mirror(factory, Task, task.id, providers, draft_for=lambda s, t, d: None)
    assert mirror_row(factory, task.id).mirror_status == "failed" and g.calls == [] and m.calls == []


def test_prepare_returning_a_name_that_is_not_a_mapped_column_raises(host_session):
    """A method or class attribute of the model is not a column: ``hasattr`` alone would let it through."""
    for name in ("metadata", "__tablename__", "registry"):
        with pytest.raises(ValueError, match=name):
            make(host_session, prepare=lambda s, t, a, e, name=name: {name: "x"})
