"""``Host.id_pattern``: a host overrides the op-id rule; the default and the wire cap stay as they were."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from conftest import Base, make_host, op
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bond_sync_py import Host, UploadRequest, apply

WIDE = re.compile(r"[A-Za-z0-9._:-]{1,200}")
BAD_IDS = json.loads((Path(__file__).resolve().parents[3] / "fixtures" / "sync" / "bad_ids.json").read_text())


def verdict(factory, host, ctx, id_):
    r = apply(factory, host, ctx, op(id_=id_, title="t"))
    return r.status, r.code, r.message


def test_host_id_pattern_admits_long_ids(factory, ctx):
    dm = f"thr-dm-{uuid4()}-{uuid4()}"
    pair = f"{uuid4()}:{uuid4()}"
    assert (len(dm), len(pair)) == (80, 73)
    with_pattern = make_host(id_pattern=WIDE)
    without = make_host()
    for id_ in (dm, pair):
        assert verdict(factory, with_pattern, ctx, id_) == ("ok", None, None)
        assert verdict(factory, without, ctx, id_) == ("rejected", "invalid", "That id is not valid")


def test_host_id_pattern_still_refuses(factory, ctx):
    host = make_host(id_pattern=WIDE)
    for bad in ("x" * 201, "has space"):
        assert verdict(factory, host, ctx, bad) == ("rejected", "invalid", "That id is not valid")
    assert apply(factory, host, ctx, op(id_="a\x00b", title="t")).code == "invalid"
    anything = make_host(id_pattern=re.compile(r".{1,200}", re.DOTALL))
    assert verdict(factory, anything, ctx, "a\x00b") == ("rejected", "invalid", "That value is not valid")


def test_wire_cap_is_the_envelope_not_the_host():
    """No host pattern can widen the wire: the envelope refuses 257 chars before any Host is consulted (the legacy
    host test posts the same id through a route with a 300-wide pattern and gets a 422)."""
    UploadRequest.model_validate({"ops": [{"seq": 0, "op": "put", "table": "items", "id": "x" * 256, "data": {}}]})
    with pytest.raises(ValidationError):
        UploadRequest.model_validate({"ops": [{"seq": 0, "op": "put", "table": "items", "id": "x" * 257, "data": {}}]})


def test_default_id_rule_unchanged(factory, ctx):
    """``id_pattern=None`` is the default rule. The anchor against the rule itself is
    test_fixtures.py::test_bad_ids_fixture_against_dispatcher; this pins that None means exactly that."""
    routes = make_host().routes
    engine = sa.create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    other = sessionmaker(bind=engine, expire_on_commit=False)  # a second database: the same id twice would conflict
    plain, explicit = Host(routes=routes), Host(routes=routes, id_pattern=None)
    for id_ in BAD_IDS["ok"] + BAD_IDS["invalid"]:
        got = verdict(factory, plain, ctx, id_)
        assert got == verdict(other, explicit, ctx, id_), repr(id_)
        expected = ("ok", None, None) if id_ in BAD_IDS["ok"] else ("rejected", "invalid", "That id is not valid")
        assert got == expected, repr(id_)


@pytest.mark.parametrize("bad", ["[a-z]+", re.compile(rb"[a-z]+"), 42])
def test_host_refuses_a_pattern_that_is_not_a_compiled_str_pattern(bad):
    with pytest.raises(TypeError):
        Host(routes={}, id_pattern=bad)


def test_host_fields_append_only():
    names = ["routes", "tables", "single_action", "rest_only", "reject_for", "already_written", "client_bools",
             "client_json"]
    assert [f.name for f in dataclasses.fields(Host)] == [*names, "id_pattern"]
    assert Host(routes={}).id_pattern is None
