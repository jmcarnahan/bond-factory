"""PUT of the body `TaskPatch.toJson` produces: with `done` an unticked item is unticked; the pre-fix body keeps it."""

import pytest
from connections_util import headers
from tasks_util import make


@pytest.fixture
def h(client):
    return headers(client)


def ticked(client, h):
    item = make(client, h, checklist=[{"text": "one"}])
    cid = item["checklist"][0]["id"]
    done = client.put(f"/tasks/{item['id']}/checklist/{cid}", json={"done": True}, headers=h).json()
    assert done["checklist"][0]["done_at"]
    return item["id"], cid, done["checklist"][0]["done_at"]


def test_put_with_done_false_unticks(client, h):
    tid, cid, _ = ticked(client, h)
    body = {"checklist": [{"id": cid, "text": "one", "done": False, "done_at": None}]}
    assert client.put(f"/tasks/{tid}", json=body, headers=h).json()["checklist"][0]["done_at"] is None


def test_put_of_the_pre_fix_body_keeps_the_tick(client, h):
    tid, cid, stamp = ticked(client, h)
    body = {"checklist": [{"id": cid, "text": "one", "done_at": None}]}
    assert client.put(f"/tasks/{tid}", json=body, headers=h).json()["checklist"][0]["done_at"] == stamp
