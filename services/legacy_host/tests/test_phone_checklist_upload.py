"""A tick and an untick from the legacy phone store, replayed one request at a time.

`fixtures/legacy_host/upload_phone_checklist.json` is recorded by `demos/legacy_phone/test/checklist_test.dart` (stage two, the
table after the app adds the SDK columns): a create with two items, the tick of item `a`, then its untick. The phone sends
`done: false` with every unticked item (a ticked one sends its stamp), so the untick is a real untick: the server's item loses its `done_at`.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sync_util import load, raw, upload

FILE = "upload_phone_checklist.json"


def send(client, request: dict) -> None:
    response = upload(client, request["user"], request["body"])
    assert response.status_code == 200, response.text
    assert [r["status"] for r in response.json()["results"]] == ["ok"] * len(request["body"]["ops"]), response.json()


def items(app) -> list[dict]:
    (cell,) = raw(app, "ck-1", "checklist")
    return json.loads(cell) if isinstance(cell, str) else cell


def test_only_an_item_the_user_unticked_says_done_false():
    requests = load(FILE)["requests"]
    said = [[("done" in i) for i in json.loads(r["body"]["ops"][0]["data"]["checklist"])] for r in requests]
    assert said == [[False, False], [False, False], [True, False], [False, False, False]]  # only the untick step names `done`
    for request in requests:
        for item in json.loads(request["body"]["ops"][0]["data"]["checklist"]):
            assert item.get("done") is not True


def test_a_tick_stamps_the_item_and_an_untick_clears_it(app, client):
    create, tick, untick, add = load(FILE)["requests"]
    send(client, create)
    first = items(app)
    assert [(i["id"], i["text"], i.get("done_at")) for i in first] == [("a", "Bring ID", None), ("b", "Sign form", None)]
    send(client, tick)
    ticked = items(app)
    phone_stamp = json.loads(tick["body"]["ops"][0]["data"]["checklist"])[0]["done_at"]  # 2026-03-11T20:01:00.000Z
    assert ticked[0]["done_at"] is not None and ticked[1].get("done_at") is None
    assert ticked[0]["done_at"].rstrip("Z").split(".")[0] == phone_stamp.rstrip("Z").split(".")[0]  # the phone's time, not the host's
    assert [(i["id"], i["text"]) for i in ticked] == [("a", "Bring ID"), ("b", "Sign form")]
    send(client, untick)
    unticked = items(app)
    assert unticked[0].get("done_at") is None and unticked[1].get("done_at") is None
    assert [(i["id"], i["text"]) for i in unticked] == [("a", "Bring ID"), ("b", "Sign form")]
    send(client, add)
    added = items(app)
    assert [(i["id"], i["text"]) for i in added] == [("a", "Bring ID"), ("b", "Sign form"), ("c", "Pay fee")]
    assert all(i.get("done_at") is None for i in added)


def test_a_stale_resend_does_not_untick_another_writers_tick(app, client):
    create, _tick, _untick, add = load(FILE)["requests"]
    send(client, create)
    # another writer (the web, say) ticks item a on the server between the phone's steps
    stamp = "2026-11-08T09:00:00Z"
    with app.state.engine.begin() as conn:
        conn.execute(text("UPDATE tasks SET checklist = :c WHERE id = 'ck-1'"),
                     {"c": json.dumps([{"id": "a", "text": "Bring ID", "done_at": stamp}, {"id": "b", "text": "Sign form", "done_at": None}])})
    send(client, add)  # the phone never ticked or unticked here: its list re-sends `a` without `done`
    kept = {i["id"]: i.get("done_at") for i in items(app)}
    assert kept["a"] is not None and kept["a"].startswith("2026-11-08T09:00:00")  # the tick of the other writer stays
    assert set(kept) == {"a", "b", "c"}
