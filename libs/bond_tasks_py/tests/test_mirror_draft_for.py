"""sync_mirror ``draft_for`` hook and the failed status for a draft that cannot be built."""
from dataclasses import replace
from datetime import timedelta

from conftest import Task
from test_mirror import make, row, setup_pair

from bond_tasks_py import sync_mirror


def run_with(factory, task, providers, draft_for):
    sync_mirror(factory, Task, task.id, providers, draft_for=draft_for)


def test_draft_for_receives_session_and_task(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    seen = []

    def hook(s, t, draft):
        seen.append((s.get(Task, t.id) is not None, t.id, t.title, draft.subject))
        return draft

    run_with(factory, task, providers, hook)
    assert seen == [(True, task.id, "Send docs", "Send docs")]
    assert row(factory, task.id).mirror_status == "mirrored" and list(g.events) == ["ev-1"]


def test_draft_for_replaces_body_and_end(factory, session):
    g, _, providers = setup_pair()
    task = make(session, due_time="09:00")

    def hook(s, t, draft):
        return replace(draft, body="Open: /tasks/x", end=draft.start + timedelta(minutes=90), categories=("Work",),
                       reminder_minutes=5)

    run_with(factory, task, providers, hook)
    sent = g.calls[0][1]
    assert sent.body == "Open: /tasks/x" and sent.categories == ("Work",) and sent.reminder_minutes == 5
    assert g.events["ev-1"]["end"] - g.events["ev-1"]["start"] == timedelta(minutes=90)


def test_draft_for_none_is_unchanged(factory, session):
    g, _, providers = setup_pair()
    plain_g, _, plain_providers = setup_pair()
    task, other = make(session), make(session)
    run_with(factory, task, providers, None)
    sync_mirror(factory, Task, other.id, plain_providers)
    assert g.calls[0][1] == plain_g.calls[0][1]


def test_draft_for_raise_marks_failed(factory, session):
    g, _, providers = setup_pair()
    task = make(session)

    def hook(s, t, draft):
        raise RuntimeError("boom")

    run_with(factory, task, providers, hook)  # does not raise
    assert row(factory, task.id).mirror_status == "failed" and g.calls == []
    run_with(factory, task, providers, None)  # the next sync retries
    assert row(factory, task.id).mirror_status == "mirrored"


def test_malformed_due_marks_failed(factory, session):
    g, _, providers = setup_pair()
    task = make(session, due_time="09:00")
    with factory() as s:
        s.get(Task, task.id).due_time = "9am"
        s.commit()
    sync_mirror(factory, Task, task.id, providers)
    assert row(factory, task.id).mirror_status == "failed" and g.calls == []
