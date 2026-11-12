"""The public surface and the shared fixtures that pin the ids and the stages."""

import json
from datetime import time
from pathlib import Path

import pytest
from conftest import Ledger, Task
from sqlalchemy import inspect

import bond_tasks_py as lib
from bond_tasks_py import (
    DefaultPermissions,
    SettingsUpdate,
    UserPrefs,
    dialect_insert,
    fnv1a31,
    notice_id,
)
from bond_tasks_py.notify_protocols import NOTICE_ACTIONS, NOTICE_CATEGORY, STAGES

FIXTURES = Path(__file__).resolve().parents[2].parent / "fixtures" / "tasks"
PREFS = UserPrefs()


def test_all_exports_exist():
    assert not [name for name in lib.__all__ if not hasattr(lib, name)]
    assert len(lib.__all__) == len(set(lib.__all__))


def test_the_existing_public_names_are_still_exported():
    for name in ("TASK_COLUMNS", "ITEM_KEYS", "JOB_TYPE", "Scheduler", "sync_routes", "compute_remind_at",
                 "fire_reminder", "schedule_reminder", "task_item", "TasksMixin", "create", "summary"):
        assert name in lib.__all__


def test_notice_ids_reproduce_the_shared_fixture():
    cases = json.loads((FIXTURES / "notice_ids.json").read_text())
    assert len(cases) >= 8
    for case in cases:
        nid = notice_id(case["task_id"], case["user_id"], case["stage"], case["seq"], case["token"])
        assert nid == case["notice_id"] and len(nid) == 32
        assert fnv1a31(nid) == case["local_id"] and 0 <= case["local_id"] <= 0x7FFFFFFF


def test_fnv1a_known_values():
    assert fnv1a31("") == 2166136261 & 0x7FFFFFFF
    assert fnv1a31("a") == 0xE40C292C & 0x7FFFFFFF  # the published FNV-1a 32-bit of "a"


def test_stage_fixture_notice_ids_match():
    cases = json.loads((FIXTURES / "stage_times.json").read_text())
    assert len(cases) >= 24
    for case in cases:
        if case["current"] is None:
            assert case["notice_id"] is None and case["sendable"] is False
        else:
            cur, task = case["current"], case["task"]
            expected = notice_id(task["id"], case["user_id"], cur["stage"], cur["seq"], case["token"])
            assert case["notice_id"] == expected and cur["stage"] in STAGES


def test_stage_fixture_lists_are_consistent():
    cases = json.loads((FIXTURES / "stage_times.json").read_text())
    assert len(cases) >= 60
    for case in cases:
        assert case["effective_zone"] == (case["prefs"]["time_zone"] or case["app_tz"])
        stages = case["stages"]
        keys = [(s["stage"], s["seq"]) for s in stages]
        assert len(keys) == len(set(keys)), case["name"]
        assert [s["at"] for s in stages] == sorted(s["at"] for s in stages), case["name"]
        for s in stages:
            assert set(s) == {"stage", "seq", "at", "last", "send_at"}
            assert s["send_at"] is None or s["send_at"] >= s["at"]
            assert s["last"] == (s["stage"] == "past" and s["seq"] == case["max_past"])
        cur = case["current"]
        if cur is not None:
            assert {"stage": cur["stage"], "seq": cur["seq"], "at": cur["at"], "last": cur["last"]} == {
                k: v for k, v in next(s for s in stages if (s["stage"], s["seq"]) == (cur["stage"], cur["seq"])).items()
                if k != "send_at"}
            assert (cur["stage"], cur["seq"]) in keys


def test_default_permissions_are_todays_rules():
    permissions = DefaultPermissions()
    task = Task(owner_user_id="owner", assigned_user_id="assignee")
    assert permissions.can_edit(task, "owner") and permissions.can_edit(task, "assignee")
    assert not permissions.can_edit(task, "other")
    assert permissions.can_own(task, "owner") and not permissions.can_own(task, "assignee")
    assert permissions.can_complete(task, "assignee") and not permissions.can_complete(task, "other")


def test_a_missing_user_id_can_do_nothing():
    permissions = DefaultPermissions()
    unassigned = Task(owner_user_id="owner", assigned_user_id=None)
    for user_id in (None, ""):
        assert not permissions.can_edit(unassigned, user_id)
        assert not permissions.can_own(unassigned, user_id)
        assert not permissions.can_complete(unassigned, user_id)
    assert not permissions.can_edit(Task(owner_user_id="owner", assigned_user_id=""), "")


def test_stage_send_at_defaults_to_none():
    from datetime import datetime

    from bond_tasks_py import StageTime

    stage = StageTime("due", 0, datetime(2026, 3, 12, 16, 30))
    assert stage.send_at is None and stage.last is False


def test_the_due_stage_is_always_sendable_and_close_follows_the_task_kind():
    cases = json.loads((FIXTURES / "stage_times.json").read_text())
    for case in cases:
        cur = case["current"]
        if cur and cur["stage"] == "due":
            assert case["sendable"] is True, case["name"]
        for stage in case["stages"]:
            if stage["stage"] == "due" or (stage["stage"] == "close" and case["task"]["due_time"]):
                assert stage["send_at"] == stage["at"], case["name"]
    named = {case["name"]: case for case in cases}
    assert named["dateonly_due_at_1701_sendable"]["sendable"] is True
    assert named["dateonly_due_at_1714_sendable"]["sendable"] is True
    assert named["dateonly_past0_at_1715_quiet"]["sendable"] is False
    unknown = named["timed_due_at_unknown"]
    assert unknown["current"] is None and unknown["stages"] == [] and unknown["token"] == ""


def test_dialect_insert_on_sqlite_has_on_conflict(session):
    assert hasattr(dialect_insert(session, Ledger), "on_conflict_do_nothing")


def test_dialect_insert_refuses_other_dialects():
    class Dialect:
        name = "mysql"

    class Bind:
        dialect = Dialect()

    class FakeSession:
        def get_bind(self):
            return Bind()

    with pytest.raises(NotImplementedError):
        dialect_insert(FakeSession(), Ledger)


def test_constants_and_prefs_defaults():
    assert STAGES == ("close", "due", "past")
    assert NOTICE_ACTIONS == ("done", "snooze", "cancel") and NOTICE_CATEGORY == "bond.task"
    assert lib.LINK_KIND_CONTACT == "contact" and lib.USE_DEFAULT_REMINDER == -3
    assert (PREFS.time_zone, PREFS.start_of_day, PREFS.end_of_day, PREFS.lead_minutes) == (
        None, time(8, 0), time(17, 0), 60)


def test_settings_update_fields_are_all_optional():
    assert SettingsUpdate().model_fields_set == set()
    assert SettingsUpdate(start_of_day="07:30", lead_minutes=0).model_fields_set == {"start_of_day", "lead_minutes"}


@pytest.mark.postgres
def test_pg_engine_fixture_creates_the_tables(pg_engine):
    assert "task_notice_ledger" in inspect(pg_engine).get_table_names()
