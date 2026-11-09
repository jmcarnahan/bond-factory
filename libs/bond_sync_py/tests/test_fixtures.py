import re

import jwt
import pytest
from conftest import FIXTURES, load_fixture
from pydantic import ValidationError

from bond_sync_py import OpResult, UploadRequest, UploadResponse, apply, upload

ID_OK = re.compile(r"[A-Za-z0-9_-]{1,64}")


def test_every_fixture_is_small_json():
    files = sorted(FIXTURES.glob("*.json"))
    assert len(files) >= 9
    for path in files:
        assert path.stat().st_size < 25_000, path.name
        load_fixture(path.name)


@pytest.mark.parametrize("name", ["upload_request_ok.json", "upload_request_mixed.json"])
def test_valid_requests_parse_and_round_trip(name):
    raw = load_fixture(name)
    body = UploadRequest.model_validate(raw)
    assert [o.seq for o in body.ops] == sorted(o.seq for o in body.ops)
    dumped = body.model_dump(exclude_none=True, exclude_defaults=False)
    assert dumped["transaction_id"] == raw["transaction_id"]


def test_too_many_ops_is_refused():
    raw = load_fixture("upload_request_too_many_ops.json")
    assert len(raw["ops"]) == 101
    with pytest.raises(ValidationError):
        UploadRequest.model_validate(raw)


def test_duplicate_seq_is_refused():
    with pytest.raises(ValidationError, match="unique"):
        UploadRequest.model_validate(load_fixture("upload_request_dup_seq.json"))


def test_exactly_100_ops_is_accepted():
    raw = load_fixture("upload_request_too_many_ops.json")
    raw["ops"] = raw["ops"][:100]
    assert len(UploadRequest.model_validate(raw).ops) == 100


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        UploadRequest.model_validate({"ops": [], "user_id": "someone-else"})
    with pytest.raises(ValidationError):
        UploadRequest.model_validate({"ops": [{"seq": 0, "op": "put", "table": "t", "id": "a", "extra": 1}]})


def test_field_limits():
    base = {"seq": 0, "op": "put", "table": "t", "id": "a", "data": {}}
    for patch in ({"seq": -1}, {"op": "upsert"}, {"table": ""}, {"table": "t" * 65}, {"id": "x" * 257}, {"action": ""},
                  {"action": "a" * 33}):
        with pytest.raises(ValidationError):
            UploadRequest.model_validate({"ops": [{**base, **patch}]})


def test_bad_ids_fixture_against_dispatcher(factory, host, ctx):
    ids = load_fixture("bad_ids.json")
    for good in ids["ok"]:
        assert ID_OK.fullmatch(good)
        body = UploadRequest.model_validate({"ops": [{"seq": 0, "op": "put", "table": "items", "id": good,
                                                      "data": {"title": "t"}}]})
        assert upload(factory, host, ctx, body).results[0].status == "ok", good
    for bad in ids["invalid"]:
        body = UploadRequest.model_validate({"ops": [{"seq": 0, "op": "put", "table": "items", "id": bad,
                                                      "data": {"title": "t"}}]})
        result = apply(factory, host, ctx, body.ops[0])
        assert (result.status, result.code) == ("rejected", "invalid"), repr(bad)
    for too_long in ids["envelope_422"]:
        with pytest.raises(ValidationError):
            UploadRequest.model_validate({"ops": [{"seq": 0, "op": "put", "table": "items", "id": too_long}]})


def test_response_fixtures_parse_and_omit_unset_keys():
    for name in ("upload_response_mixed.json", "upload_response_all_codes.json"):
        raw = load_fixture(name)
        response = UploadResponse.model_validate({"results": raw["results"], "server_now": raw["server_now"]})
        assert response.wire()["results"] == raw["results"]
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", raw["server_now"])


def test_all_codes_fixture_covers_every_verdict():
    codes = {r.get("code") for r in load_fixture("upload_response_all_codes.json")["results"]}
    assert {"invalid", "unsupported", "conflict", "not_found", "forbidden", "rate_limited", "server_error",
            "already"} <= codes


def test_op_result_wire_omits_none():
    assert OpResult(seq=3, status="ok").wire() == {"seq": 3, "status": "ok"}


def test_example_token_verifies_with_example_jwks():
    claims_fx = load_fixture("sync_token_claims.json")
    jwk = load_fixture("jwks_example.json")["keys"][0]
    assert jwk["alg"] == "ES256" and jwk["kid"] == claims_fx["header"]["kid"]
    key = jwt.algorithms.ECAlgorithm.from_jwk({k: jwk[k] for k in ("kty", "crv", "x", "y")})
    decoded = jwt.decode(claims_fx["example_token"], key, algorithms=["ES256"], audience="powersync",
                         options={"verify_exp": False})
    assert decoded == claims_fx["claims"]
    assert claims_fx["claims"]["exp"] - claims_fx["claims"]["iat"] == claims_fx["seconds_valid"]
    assert jwt.get_unverified_header(claims_fx["example_token"])["kid"] == "bond-sync-1"
