"""The legacy phone's settings over `POST /sync/upload`, replayed one request at a time.

`fixtures/legacy_host/upload_phone_settings.json` is recorded by `demos/legacy_phone/test/settings_test.dart`: a date-only task,
then a zone and end-of-day write into the phone's own `user_prefs` (columns `tz`, `day_end`; the row id is the user id), then
a reset of the end of day. The server's row holds `tz` and `day_end`, the date-only task's due instant follows, and the reset
returns the default.
"""

from __future__ import annotations

from sqlalchemy import text
from sync_util import load, raw, upload

FILE = "upload_phone_settings.json"


def send(client, request: dict) -> dict:
    response = upload(client, request["user"], request["body"])
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["ok"] * len(request["body"]["ops"]), results
    return response.json()


def prefs(app, user: str = "u-owner"):
    with app.state.engine.connect() as conn:
        return conn.execute(text("SELECT tz, day_start, day_end, remind_lead FROM user_prefs WHERE uid = :u"), {"u": user}).first()


def test_the_phone_writes_the_apps_own_names_and_the_row_id_is_the_user():
    put, patch = load(FILE)["requests"][1]["body"]["ops"][0], load(FILE)["requests"][2]["body"]["ops"][0]
    assert (put["op"], put["table"], put["id"], set(put["data"])) == ("put", "user_prefs", "u-owner", {"tz", "day_end"})
    assert (patch["op"], patch["data"]) == ("patch", {"day_end": None})


def test_zone_and_end_of_day_arrive_then_the_reset_returns_the_default(app, client):
    task, write, reset = load(FILE)["requests"]
    send(client, task)
    before = raw(app, "ph-s1", "due_at")
    send(client, write)
    row = prefs(app)
    assert (row.tz, row.day_end) == ("America/Denver", "18:30")
    after = raw(app, "ph-s1", "due_at")
    assert before == ('2026-11-20 17:00:00.000000',)  # 17:00 in the host's default zone
    assert after == ('2026-11-21 01:30:00.000000',)  # 18:30 on the 20th in America/Denver (UTC-7), recomputed in the op
    send(client, reset)
    row = prefs(app)
    assert (row.tz, row.day_end) == ("America/Denver", None)  # NULL: the app default again
    assert raw(app, "ph-s1", "due_at") == ("2026-11-21 00:00:00.000000",)  # the default 17:00 in the kept zone
