"""A host that opts in to a wider op-id rule (`create_app(sync_id_pattern=...)`); the default stays strict."""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from conftest import TEST_NOW, seed
from fastapi.testclient import TestClient
from sqlalchemy import text
from sync_util import upload
from test_notices_sync import DEVICE_TIME, add_notice

from legacy_host.app import create_app

WIDE = re.compile(r"[A-Za-z0-9._:-]{1,200}")


@pytest.fixture
def wide_app(tmp_path):
    app = create_app(f"sqlite:///{tmp_path}/wide.db", sync_id_pattern=WIDE)
    app.state.clock.freeze(TEST_NOW)
    seed(app)
    return app


def read(client, notice_id):
    body = {"transaction_id": 1, "ops": [{"seq": 0, "op": "patch", "table": "notices", "id": notice_id,
                                           "data": {"read_at": DEVICE_TIME}}]}
    response = upload(client, "u-owner", body)
    assert response.status_code == 200, response.text
    return response.json()["results"][0]


def read_at(app, notice_id):
    with app.state.engine.connect() as conn:
        return conn.execute(text("SELECT read_at FROM notices WHERE id = :i"), {"i": notice_id}).scalar_one()


@pytest.mark.parametrize("make", [lambda: f"{uuid4()}:{uuid4()}", lambda: f"thr-dm-{uuid4()}-{uuid4()}"])
def test_opted_in_host_takes_long_and_punctuated_ids(wide_app, make):
    notice_id = make()
    add_notice(wide_app, notice_id)
    assert read(TestClient(wide_app), notice_id) == {"seq": 0, "status": "ok"}
    assert read_at(wide_app, notice_id) is not None


def test_a_wider_pattern_cannot_widen_the_wire(tmp_path):
    app = create_app(f"sqlite:///{tmp_path}/w300.db", sync_id_pattern=re.compile(r"[A-Za-z0-9_-]{1,300}"))
    app.state.clock.freeze(TEST_NOW)
    seed(app)
    body = {"transaction_id": 1, "ops": [{"seq": 0, "op": "patch", "table": "notices", "id": "x" * 257,
                                           "data": {"read_at": DEVICE_TIME}}]}
    assert upload(TestClient(app), "u-owner", body).status_code == 422


def test_default_host_still_refuses_them(app, client):
    notice_id = f"{uuid4()}:{uuid4()}"
    add_notice(app, notice_id)
    result = read(client, notice_id)
    assert (result["status"], result["code"]) == ("rejected", "invalid")
    assert read_at(app, notice_id) is None
