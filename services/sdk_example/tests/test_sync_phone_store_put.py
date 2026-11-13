"""The phone store writes `checklist` and `links` as JSON text; the stock server takes it on `/sync/upload`."""

import json

import pytest
from connections_util import headers

from sdk_example.models.tasks import Task

ITEMS = json.dumps([{"id": "c1", "text": "A", "done": False}])
LINKS = json.dumps([{"kind": "contact", "id": "c-sam-rivera", "label": "Sam"}])


def send(client, h, op, task_id, data, txn=1):
    body = {"transaction_id": txn, "ops": [{"seq": 0, "op": op, "table": "tasks", "id": task_id, "data": data}]}
    reply = client.post("/sync/upload", json=body, headers=h)
    assert reply.status_code == 200, reply.text
    return reply.json()["results"][0]


@pytest.mark.parametrize("checklist,links", [("[]", "[]"), (ITEMS, LINKS)])
def test_a_put_with_json_text_checklist_and_links_is_ok(client, app, checklist, links):
    h = headers(client)
    result = send(client, h, "put", "t-phone", {"title": "From phone", "checklist": checklist, "links": links})
    assert result["status"] == "ok", result
    with app.state.session_factory() as session:
        task = session.get(Task, "t-phone")
        assert len(task.checklist) == len(json.loads(checklist)) and len(task.links) == len(json.loads(links))
    if checklist != "[]":
        item = client.get("/tasks/t-phone", headers=h).json()["checklist"][0]
        assert item["id"] == "c1" and item["text"] == "A"


def test_a_patch_with_json_text_and_malformed_text(client):
    h = headers(client)
    assert send(client, h, "put", "t-p", {"title": "x"})["status"] == "ok"
    assert send(client, h, "patch", "t-p", {"checklist": ITEMS}, txn=2)["status"] == "ok"
    assert client.get("/tasks/t-p", headers=h).json()["checklist"][0]["text"] == "A"
    bad = send(client, h, "patch", "t-p", {"checklist": "not json"}, txn=3)
    assert bad["status"] == "rejected" and bad["code"] == "invalid"
