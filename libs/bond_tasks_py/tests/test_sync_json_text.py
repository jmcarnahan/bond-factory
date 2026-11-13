"""A phone store writes `checklist` and `links` as JSON text; sync writes read it like the list form."""

import json
from dataclasses import dataclass

import pytest
from conftest import NOW, Task
from pydantic import ValidationError

from bond_tasks_py import sync_routes

ROUTE = sync_routes(Task, now=lambda: NOW)[("tasks", None)]
ITEMS = [{"id": "c1", "text": "A", "done": False}]
LINKS = [{"kind": "contact", "id": "c-1", "label": "Sam"}]


@dataclass
class Op:
    id: str
    op: str


@dataclass
class Ctx:
    user: object
    background: object = None


def call(session, op, task_id, data):
    return ROUTE.handler(session, Ctx("u1"), Op(task_id, op), data)


def stored(session, task_id):
    task = session.get(Task, task_id)
    return [{k: v for k, v in i.items() if k != "done_at"} for i in task.checklist], task.links


@pytest.mark.parametrize("op", ["put", "patch"])
def test_text_stores_the_same_value_as_the_list_form(session, op):
    call(session, "put", "list", {"title": "A", "checklist": ITEMS, "links": LINKS})
    if op == "put":
        call(session, "put", "text", {"title": "A", "checklist": json.dumps(ITEMS), "links": json.dumps(LINKS)})
    else:
        call(session, "put", "text", {"title": "A"})
        call(session, "patch", "text", {"checklist": json.dumps(ITEMS), "links": json.dumps(LINKS)})
    assert stored(session, "text") == stored(session, "list") and stored(session, "text")[0]


def test_empty_array_text_is_an_empty_list(session):
    call(session, "put", "t", {"title": "A", "checklist": "[]", "links": "[]"})
    assert stored(session, "t") == ([], [])
    call(session, "patch", "t", {"checklist": json.dumps(ITEMS)})
    call(session, "patch", "t", {"checklist": "[]"})
    assert stored(session, "t") == ([], [])


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_text_is_not_sent(session, blank):
    call(session, "put", "t", {"title": "A", "checklist": json.dumps(ITEMS)})
    call(session, "patch", "t", {"title": "B", "checklist": blank, "links": blank})
    assert stored(session, "t")[0][0]["text"] == "A" and session.get(Task, "t").title == "B"
    call(session, "put", "u", {"title": "A", "checklist": blank, "links": blank})
    assert stored(session, "u") == ([], [])


@pytest.mark.parametrize("column", ["checklist", "links"])
@pytest.mark.parametrize("text", ["not json", "[{", '{"a": 1}', "5", '"x"', "null"])
@pytest.mark.parametrize("op", ["put", "patch"])
def test_malformed_or_non_list_text_is_the_wrong_type_refusal(session, column, text, op):
    call(session, "put", "t", {"title": "A"})
    with pytest.raises(ValidationError) as caught:  # what a host maps to the `invalid` verdict, as a wrong type does today
        call(session, op, "t" if op == "patch" else "new", {"title": "A", column: text})
    wrong = pytest.raises(ValidationError)
    with wrong as ref:
        call(session, op, "t" if op == "patch" else "new2", {"title": "A", column: 5})
    assert caught.value.errors()[0]["loc"][0] == ref.value.errors()[0]["loc"][0] == column


def test_list_form_is_unchanged(session):
    call(session, "put", "t", {"title": "A", "checklist": ITEMS, "links": LINKS})
    assert stored(session, "t")[0][0]["text"] == "A" and stored(session, "t")[1][0]["id"] == "c-1"


DEEP = ["[" * 200000 + "]" * 200000, '{"a":' * 100000, "[" * 200000]


@pytest.mark.parametrize("column", ["checklist", "links"])
@pytest.mark.parametrize("op", ["put", "patch"])
@pytest.mark.parametrize("text", DEEP)
def test_deeply_nested_text_is_the_same_refusal_not_a_crash(session, column, op, text):
    call(session, "put", "t", {"title": "A"})
    with pytest.raises(ValidationError):
        call(session, op, "t" if op == "patch" else "new", {"title": "A", column: text})
