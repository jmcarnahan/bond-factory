"""Trait 6: tables that pre-date the modules. Grants: `file_share_grants` with other column names, a NULLABLE count
and `created_at`, and no `purpose`/`owner_*`/`last_*`/`updated_at` (the adoption migration ADDS those, see
`legacy_host/legacy_ddl.py`). Settings: `user_prefs` with other column names, NULLs, and the app's own `theme`."""

from datetime import datetime

import bond_tasks_py as tasks
import pytest
from conftest import TEST_NOW, as_user
from fastapi.testclient import TestClient
from legacy_db import legacy_app
from sqlalchemy import text

from legacy_host.models import Attachment, Task, UserPrefs

OWNER = as_user("u-owner")
TOKEN = "tok-old-1"
NOW = TEST_NOW.replace(tzinfo=None)


def old_grant(connection, grant_id, token, *, max_downloads=3, hits=None, expires="2026-12-01 00:00:00"):
    from bond_storage import hash_token
    connection.execute(text(
        "INSERT INTO file_share_grants (id, token_hash, attachment_id, expires_at, max_downloads, hits, sender_id, "
        "created_at, recipient_note) VALUES (:id, :h, 'att-1', :exp, :max, :hits, 'u-owner', NULL, 'for Pat')"),
        {"id": grant_id, "h": hash_token(token), "exp": expires, "max": max_downloads, "hits": hits})


def old_prefs(connection):
    stamp = "2026-11-01 09:00:00"
    for uid, tz, start, end, lead, theme in [("u-owner", None, None, None, None, "dark"),
                                             ("u-editor", "America/Chicago", "07:30", None, 45, None)]:
        connection.execute(text(
            "INSERT INTO user_prefs (uid, tz, day_start, day_end, remind_lead, theme, updated_at) "
            f"VALUES (:uid, :tz, :s, :e, :l, :t, '{stamp}')"), {"uid": uid, "tz": tz, "s": start, "e": end, "l": lead, "t": theme})


@pytest.fixture
def old(tmp_path):
    def fill(connection):
        old_grant(connection, "g-1", TOKEN)
        old_grant(connection, "g-single", "tok-single", max_downloads=1)
        old_grant(connection, "g-open", "tok-open", max_downloads=None)
        old_grant(connection, "g-expired", "tok-expired", expires="2026-11-01 00:00:00")
        old_prefs(connection)

    app = legacy_app(tmp_path / "old.db", fill)
    with app.state.session_factory() as session:
        session.add(Attachment(id="att-1", storage_key="k/1", filename="form.pdf", content_type="application/pdf"))
        session.commit()
    return app, TestClient(app)


def counts(app):
    with app.state.session_factory() as session:
        return {r[0]: r[1] for r in session.execute(text("SELECT id, hits FROM file_share_grants"))}


# grants


def test_old_grant_resolves_and_claims_with_a_null_count(old):
    app, client = old
    assert counts(app)["g-1"] is None
    r = client.get(f"/shares/{TOKEN}")
    assert r.status_code == 200, r.text
    assert (r.json()["filename"], r.json()["downloads"], r.json()["recipient_note"]) == ("form.pdf", 1, "for Pat")
    assert counts(app)["g-1"] == 1


def test_old_grant_honours_its_cap(old):
    app, client = old
    assert [client.get(f"/shares/{TOKEN}").status_code for _ in range(4)] == [200, 200, 200, 410]
    assert counts(app)["g-1"] == 3


def test_old_single_use_grant_is_used_once(old):
    _, client = old
    assert [client.get("/shares/tok-single").status_code for _ in range(2)] == [200, 410]


def test_old_grant_without_a_cap_counts_but_never_stops(old):
    app, client = old
    assert [client.get("/shares/tok-open").status_code for _ in range(5)] == [200] * 5
    assert counts(app)["g-open"] == 5


def test_old_expired_and_unknown_links_answer_the_same(old):
    _, client = old
    bodies = [client.get(f"/shares/{t}") for t in ("tok-expired", "nope")]
    assert [b.status_code for b in bodies] == [410, 410] and bodies[0].json() == bodies[1].json()


def test_new_grant_lands_in_the_legacy_columns(old):
    app, client = old
    r = client.post("/shares", json={"attachment_id": "att-1", "max_downloads": 2, "recipient_note": "for Sam"},
                    headers=OWNER)
    assert r.status_code == 201, r.text
    with app.state.session_factory() as session:
        row = session.execute(text(
            "SELECT attachment_id, sender_id, hits, max_downloads, recipient_note, created_at, purpose "
            "FROM file_share_grants WHERE id = :id"), {"id": r.json()["id"]}).one()
    assert tuple(row)[:5] == ("att-1", "u-owner", 0, 2, "for Sam") and row[5] is not None and row[6] == "share"
    assert client.get(f"/shares/{r.json()['token']}").json()["downloads"] == 1


def test_new_grant_for_a_missing_attachment_is_404(old):
    _, client = old
    assert client.post("/shares", json={"attachment_id": "nope"}, headers=OWNER).status_code == 404
    assert client.post("/shares", json={"attachment_id": "att-1"}).status_code == 401


# settings


def test_null_prefs_follow_the_app_default(old):
    _, client = old
    body = client.get("/prefs", headers=OWNER).json()
    assert (body["time_zone"], body["start_of_day"], body["end_of_day"], body["lead_minutes"]) == (
        None, "08:00", "17:00", 60)
    assert body["overridden"] == [] and body["theme"] == "dark"


def test_an_old_explicit_day_start_is_an_override(old):
    _, client = old
    body = client.get("/prefs", headers=as_user("u-editor")).json()
    assert (body["time_zone"], body["start_of_day"], body["end_of_day"], body["lead_minutes"]) == (
        "America/Chicago", "07:30", "17:00", 45)
    assert body["overridden"] == ["time_zone", "start_of_day", "lead_minutes"]


def test_prefs_update_writes_the_legacy_columns(old):
    app, client = old
    r = client.put("/prefs", json={"start_of_day": "06:45", "end_of_day": "15:00", "time_zone": "UTC",
                                   "theme": "light", "unknown": 1}, headers=OWNER)
    assert r.status_code == 200, r.text
    with app.state.session_factory() as session:
        row = session.execute(text("SELECT tz, day_start, day_end, remind_lead, theme FROM user_prefs "
                                   "WHERE uid = 'u-owner'")).one()
    assert tuple(row) == ("UTC", "06:45", "15:00", None, "light")  # lead stays NULL = follows the default
    assert r.json()["overridden"] == ["time_zone", "start_of_day", "end_of_day"]


def test_prefs_reset_to_null_follows_the_default_again(old):
    _, client = old
    r = client.put("/prefs", json={"start_of_day": None, "lead_minutes": None}, headers=as_user("u-editor"))
    assert r.json()["start_of_day"] == "08:00" and r.json()["overridden"] == ["time_zone"]


def test_a_new_user_gets_a_row_in_the_legacy_table(old):
    app, client = old
    client.put("/prefs", json={"lead_minutes": 20}, headers=as_user("u-admin"))
    with app.state.session_factory() as session:
        assert session.execute(text("SELECT remind_lead FROM user_prefs WHERE uid = 'u-admin'")).scalar_one() == 20


def test_prefs_zone_drives_the_viewer_day(old):
    app, client = old
    # the editor stored America/Chicago: 2026-11-08 10:00 UTC is still the 8th there, and a task due the 8th is today
    client.post("/tasks", json={"id": "t-1", "title": "A", "due_date": "2026-11-08"}, headers=as_user("u-editor"))
    with app.state.session_factory() as session:
        found = tasks.today(session, task_model=Task, user_id="u-editor",
                            now=datetime(2026, 11, 8, 10, 0), viewer_zone="America/Chicago")
    assert [t.id for t in found.today] == ["t-1"]


# the probed limit


def test_prefs_row_holding_seconds_cannot_be_read_today(tmp_path):
    """LIMIT: the lib parses a stored work-day time as `HH:MM`. A legacy row that kept seconds (`08:00:00`) makes
    every read of that user's preferences fail. Pinned as it is; a host with such rows normalises them in its
    adoption migration (`UPDATE user_prefs SET day_start = substr(day_start, 1, 5)`)."""
    def fill(connection):
        connection.execute(text("INSERT INTO user_prefs (uid, day_start, updated_at) VALUES "
                                "('u-owner', '08:00:00', '2026-11-01 09:00:00')"))

    app = legacy_app(tmp_path / "secs.db", fill)
    with app.state.session_factory() as session, pytest.raises(ValueError):
        tasks.get_settings(session, UserPrefs, "u-owner")
