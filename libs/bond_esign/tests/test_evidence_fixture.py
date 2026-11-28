"""The recorded evidence sample (fixtures/esign/evidence_0.1.json) still matches what evidence() returns today."""

import json
from pathlib import Path

import pytest
from conftest import T, new_request

import bond_esign as es

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "esign" / "evidence_0.1.json"
ZERO = "0" * 64


@pytest.fixture(scope="module")
def recorded() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_is_small_and_has_the_schema(recorded):
    assert FIXTURE.stat().st_size <= 100_000
    assert recorded["schema"] == "bond.esign_evidence/0.1"
    assert set(recorded) == {"schema", "request", "signers", "events", "chain", "check"}


def test_key_sets_match_a_fresh_export(recorded, session, pdf_bytes):
    fresh = es.evidence(session, T, new_request(session, pdf_bytes))
    assert set(recorded) == set(fresh)
    # the conftest request table is the tenant variant: it has company_id, the recorded one (plain mixin) has not
    assert set(recorded["request"]) | {"company_id"} == set(fresh["request"])
    assert set(recorded["signers"][0]) == set(fresh["signers"][0])
    assert set(recorded["events"][0]) == set(fresh["events"][0])
    assert set(recorded["chain"]) == set(fresh["chain"])
    assert set(recorded["check"]) == set(fresh["check"])


def test_recorded_chain_verifies_offline_with_the_public_hash(recorded):
    request_id = recorded["request"]["id"]
    prev = ZERO
    for number, e in enumerate(recorded["events"], start=1):
        payload = {
            "request_id": request_id, "seq": e["seq"], "signer_id": e["signer_id"], "kind": e["kind"],
            "at": e["at"], "ip": e["ip"], "user_agent": e["user_agent"], "actor": e["actor"], "data": e["data"],
        }
        assert e["seq"] == number
        assert e["prev_hash"] == prev
        assert e["row_hash"] == es.row_hash(prev, payload)
        assert es.canonical(payload) == json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        prev = e["row_hash"]
    assert recorded["chain"] == {"ok": True, "count": len(recorded["events"]), "head": prev}
    assert recorded["check"] == {"ok": True, "problems": []}


def test_recorded_events_are_in_the_expected_order(recorded):
    kinds = [e["kind"] for e in recorded["events"]]
    assert kinds[0] == es.CREATED
    assert kinds[-4:] == [es.DOCUMENT_BUILT, es.COMPLETED, es.COPY_DELIVERED, es.DOWNLOADED]
    assert set(kinds) <= set(es.KINDS)


def test_data_key_sets_per_event_kind_match_a_fresh_export(recorded, session, pdf_bytes):
    from conftest import CTX, at, sign_it, signers_of

    request = new_request(session, pdf_bytes)
    signer = signers_of(session, request)[0]
    es.issue_token(session, T, signer, now=at(0))
    es.signing_view(session, T, signer, ctx=CTX, now=at(0))
    sign_it(session, signer, pdf_bytes)
    built = es.build_signed_pdf(session, T, request, pdf=pdf_bytes)
    es.complete(session, T, request, signed=built, now=at(2))
    es.record_delivery(session, T, request, channel="email", reference="msg-1", signer=signer, ctx=CTX, now=at(3))
    es.record_download(session, T, request, signer=signer, ctx=CTX, now=at(4))
    fresh: dict[str, set] = {}
    for event in es.evidence(session, T, request)["events"]:
        fresh.setdefault(event["kind"], set(event["data"]))
    pinned: dict[str, set] = {}
    for event in recorded["events"]:
        pinned.setdefault(event["kind"], set(event["data"]))
    assert set(pinned) <= set(fresh)
    for kind, keys in pinned.items():
        assert keys == fresh[kind], kind
