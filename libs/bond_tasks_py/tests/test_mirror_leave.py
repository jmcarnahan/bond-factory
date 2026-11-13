"""``MirrorDraft.leave``: fields an UPDATE must not send because the person owns them in their own calendar."""
from dataclasses import replace

import pytest
from conftest import Task
from test_mirror import edit, make, row, run, setup_pair

from bond_tasks_py import MirrorDraft, sync_mirror

LEFT = frozenset({"location", "categories", "reminder_minutes"})


def leaving(names=LEFT):
    return lambda session, task, draft: replace(draft, leave=frozenset(names))


def draft(**fields):
    from datetime import UTC, datetime
    base = {"subject": "A", "start": datetime(2026, 11, 10, tzinfo=UTC), "end": datetime(2026, 11, 11, tzinfo=UTC),
            "is_all_day": True}
    return MirrorDraft(**{**base, **fields})


def updates(g):
    return [c for c in g.calls if c[0] == "update"]


def test_default_update_sends_every_draft_field_and_never_leave(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    run(factory, task, providers)
    edit(session, task, title="Renamed")
    run(factory, task, providers)
    assert set(updates(g)[0][2]) == {"subject", "start", "end", "is_all_day", "body", "body_type", "location",
                                     "categories", "reminder_minutes"}


def test_update_omits_the_left_fields_and_create_sends_them_all(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving())
    created = g.calls[0][1]
    assert created.leave == LEFT and created.location is None  # a create owns every field
    edit(session, task, title="Renamed")
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving())
    patch = updates(g)[0][2]
    assert patch["subject"] == "Renamed" and not set(patch) & (LEFT | {"leave"})
    assert g.events["ev-1"]["subject"] == "Renamed"


def test_the_etag_path_rereads_and_still_omits_the_left_fields(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving())
    g.etags["ev-1"] = 7  # the person edited the event
    edit(session, task, title="Again")
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving())
    assert [c[0] for c in g.calls] == ["create", "update", "get", "update"]
    first, second = updates(g)
    assert first[2] == second[2] and not set(second[2]) & (LEFT | {"leave"}) and second[3] == 'W/"7"'


def test_a_not_found_update_recreates_with_the_full_draft(factory, session):
    g, _, providers = setup_pair()
    task = make(session)
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving())
    del g.events["ev-1"]
    edit(session, task, title="Again")
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving())
    assert [c[0] for c in g.calls] == ["create", "update", "create"]
    assert g.calls[-1][1].subject == "Again" and row(factory, task.id).mirror_status == "mirrored"


def test_leave_can_name_the_body_too(factory, session):
    g, _, providers = setup_pair()
    task = make(session, notes="first")
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving({"body"}))
    edit(session, task, notes="second")
    sync_mirror(factory, Task, task.id, providers, draft_for=leaving({"body"}))
    assert "body" not in updates(g)[0][2] and "location" in updates(g)[0][2]


def test_an_unknown_name_is_a_value_error_at_construction():
    with pytest.raises(ValueError, match="no draft field: colour"):
        draft(leave=frozenset({"colour"}))
    with pytest.raises(ValueError, match="no draft field: leave"):
        draft(leave=frozenset({"leave"}))


def test_the_time_fields_are_left_together_or_not_at_all():
    assert draft(leave=frozenset({"start", "end", "is_all_day"})).leave == {"start", "end", "is_all_day"}
    with pytest.raises(ValueError, match="together"):
        draft(leave=frozenset({"start"}))


def test_a_draft_for_that_returns_a_bad_leave_fails_the_row_before_any_provider_call(factory, session):
    g, _, providers = setup_pair()
    task = make(session)

    def hook(s, t, d):
        return replace(d, leave=frozenset({"colour"}))

    sync_mirror(factory, Task, task.id, providers, draft_for=hook)  # does not raise
    assert row(factory, task.id).mirror_status == "failed" and g.calls == []


@pytest.mark.parametrize("given", [["location"], ("location",), {"location"}, frozenset({"location"})])
def test_leave_takes_any_collection_of_names(given):
    assert draft(leave=given).leave == frozenset({"location"})


def test_leave_none_is_empty_and_a_string_is_refused():
    assert draft(leave=None).leave == frozenset()
    with pytest.raises(ValueError, match="not a string"):
        draft(leave="location")
