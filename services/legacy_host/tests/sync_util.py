"""Helpers for the sync and provider-edit tests: the recorded fixtures, replay, raw SQL reads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import as_user
from sqlalchemy import text

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "legacy_host"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def upload(client: Any, user: str, body: dict) -> Any:
    return client.post("/sync/upload", json=body, headers=as_user(user))


def replay(client: Any, recording: dict) -> list[dict]:
    """Post each recorded request as its user; every answer is a 200 with one result per op."""
    answers = []
    for request in recording["requests"]:
        response = upload(client, request["user"], request["body"])
        assert response.status_code == 200, response.text
        answers.append(response.json())
    return answers


def raw(app: Any, task_id: str, *columns: str) -> tuple:
    """Columns of one tasks row by raw SQL (the legacy column names, not the model's attribute names)."""
    with app.state.engine.connect() as conn:
        row = conn.execute(text(f"SELECT {', '.join(columns)} FROM tasks WHERE id = :id"), {"id": task_id}).one()
    return tuple(row)
