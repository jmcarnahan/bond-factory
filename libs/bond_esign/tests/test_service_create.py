import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from conftest import CONSENT, NOW, PLACEMENT, T, expect, kinds_of, make_pdf, new_request, signers_of
from sqlalchemy.orm import DeclarativeBase

from bond_esign import (
    AnchorRule,
    EsignEventMixin,
    EsignRequestMixin,
    EsignSignerMixin,
    Placement,
    Policy,
    SignerSpec,
    Tables,
    anchor,
    chain,
    policy_of,
    sha256_hex,
)


def test_create_writes_request_signers_and_the_created_event(session, pdf_bytes):
    request = new_request(
        session, pdf_bytes, subject_type="estimate", subject_id="E-1", company_id="co-1", meta={"k": "v"},
        signers=[SignerSpec("Pat Example", "pat@example.com", key="c-1", placement=PLACEMENT), SignerSpec("Sam Sample")],
        expires_at=NOW + timedelta(days=7),
    )  # fmt: skip
    assert request.status == "open" and request.title == "Estimate 100"
    assert request.document_sha256 == sha256_hex(pdf_bytes) and request.document_bytes == len(pdf_bytes)
    assert request.page_count == 2
    assert (request.subject_type, request.subject_id, request.company_id) == ("estimate", "E-1", "co-1")
    assert request.consent_sha256 == sha256_hex(CONSENT.text.encode())
    assert (request.consent_version, request.consent_language, request.consent_text) == (
        CONSENT.version, "en", CONSENT.text)  # fmt: skip
    assert request.policy == dataclasses.asdict(Policy()) and request.meta == {"k": "v"}
    assert request.sealed is False and request.timestamped is False
    assert request.expires_at == NOW + timedelta(days=7) and request.created_at == NOW
    first, second = signers_of(session, request)
    assert (first.position, first.name, first.email, first.key, first.status) == (0, "Pat Example", "pat@example.com", "c-1", "pending")
    assert (second.position, second.role, second.placement) == (1, "signer", None)
    assert first.placement == {"page": 2, "x": 0.2, "y": 0.8, "w": 0.3, "h": 0.06}  # -1 became page 2
    (created,) = chain(session, T, request)
    assert created.kind == "created" and set(created.data) == {
        "document_sha256", "title", "consent_version", "consent_sha256", "signers"}
    assert created.data["document_sha256"] == request.document_sha256 and created.data["title"] == request.title
    assert created.data["signers"] == [
        {"id": s.id, "position": s.position, "name": s.name, "email": s.email, "role": s.role, "key": s.key}
        for s in (first, second)
    ]


def test_placement_wins_over_anchor_and_a_found_anchor_is_resolved(session, pdf_bytes, monkeypatch):
    calls = []

    def fake(pdf, rule):
        calls.append(rule.text)
        return Placement(page=-1, x=0.5, y=0.5, w=0.2, h=0.05)

    monkeypatch.setattr(anchor, "find_anchor", fake)
    rule = AnchorRule("Accepted by (customer)")
    request = new_request(session, pdf_bytes, signers=[
        SignerSpec("Pat", placement=PLACEMENT, anchor=rule), SignerSpec("Sam", anchor=rule),
    ])  # fmt: skip
    pat, sam = signers_of(session, request)
    assert pat.placement["x"] == 0.2 and calls == ["Accepted by (customer)"]  # only Sam was searched
    assert sam.placement == {"page": 2, "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.05}


def test_anchor_not_found_leaves_placement_none_and_is_noted_on_the_event(session, pdf_bytes, monkeypatch):
    monkeypatch.setattr(anchor, "find_anchor", lambda pdf, rule: None)
    request = new_request(session, pdf_bytes, signers=[SignerSpec("Pat", anchor=AnchorRule("Sign here"))])
    assert signers_of(session, request)[0].placement is None
    assert chain(session, T, request)[0].data["anchor_missing"] == ["Sign here"]


def test_anchor_box_over_the_page_edge_is_pulled_back_in(session, pdf_bytes, monkeypatch):
    monkeypatch.setattr(anchor, "find_anchor", lambda pdf, rule: Placement(1, 0.9, 0.97, 0.3, 0.055))
    request = new_request(session, pdf_bytes, signers=[SignerSpec("Pat", anchor=AnchorRule("x"))])
    p = signers_of(session, request)[0].placement
    assert p["x"] + p["w"] <= 1 + 1e-9 and p["y"] + p["h"] <= 1 + 1e-9 and p["page"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        Placement(0, 0.1, 0.1, 0.2, 0.05), Placement(3, 0.1, 0.1, 0.2, 0.05), Placement(-3, 0.1, 0.1, 0.2, 0.05),
        Placement(1, -0.1, 0.1, 0.2, 0.05), Placement(1, 0.1, 1.5, 0.2, 0.05), Placement(1, 0.9, 0.1, 0.3, 0.05),
        Placement(1, 0.1, 0.1, 0.0, 0.05),
    ],
)  # fmt: skip
def test_a_placement_outside_the_page_or_the_page_count_is_a_value_error(session, pdf_bytes, bad):
    with pytest.raises(ValueError):
        new_request(session, pdf_bytes, signers=[SignerSpec("Pat", placement=bad)])
    with pytest.raises(ValueError):
        new_request(session, pdf_bytes, signers=[SignerSpec("Pat", date_placement=bad)])


def test_date_placement_is_resolved_too(session, pdf_bytes):
    spec = SignerSpec("Pat", placement=PLACEMENT, date_placement=Placement(-2, 0.6, 0.8, 0.2, 0.05))
    signer = signers_of(session, new_request(session, pdf_bytes, signers=[spec]))[0]
    assert signer.date_placement["page"] == 1


def test_invalid_pdf_and_oversize_pdf(session, pdf_bytes):
    with expect("invalid_pdf"):
        new_request(session, b"this is not a pdf")
    with expect("invalid_pdf"):
        new_request(session, pdf_bytes, policy=Policy(max_pdf_bytes=100))


def test_too_many_signers_and_no_signers(session, pdf_bytes):
    with expect("too_many_signers"):
        new_request(session, pdf_bytes, signers=[SignerSpec("A"), SignerSpec("B")], policy=Policy(max_signers=1))
    with pytest.raises(ValueError):
        new_request(session, pdf_bytes, signers=[])


def test_aware_expiry_is_stored_as_naive_utc(session, pdf_bytes):
    when = datetime(2026, 12, 1, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert new_request(session, pdf_bytes, expires_at=when).expires_at == datetime(2026, 12, 1, 10, 0)


def test_policy_round_trips_and_policy_of_tolerates_drift(session, pdf_bytes):
    policy = Policy(require_email_code=True, max_signers=3, typed_charset="any")
    request = new_request(session, pdf_bytes, policy=policy)
    assert policy_of(request) == policy
    request.policy = {"require_email_code": True, "from_a_future_version": 1}
    rebuilt = policy_of(request)
    assert rebuilt.require_email_code is True and rebuilt.max_signers == Policy().max_signers


def test_company_id_needs_the_tenant_mixin(session, pdf_bytes):
    class Other(DeclarativeBase):
        pass

    class R(EsignRequestMixin, Other):
        pass

    class S(EsignSignerMixin, Other):
        pass

    class E(EsignEventMixin, Other):
        pass

    from bond_esign import create_request

    with pytest.raises(ValueError):
        create_request(
            session, Tables(R, S, E), pdf=pdf_bytes, title="t", signers=[SignerSpec("A")], consent=CONSENT,
            now=NOW, company_id="co-1",
        )  # fmt: skip


def test_creating_changes_nothing_but_adds_rows_and_never_commits(session, pdf_bytes):
    request = new_request(session, pdf_bytes)
    session.rollback()
    assert session.get(T.request, request.id) is None
    assert kinds_of(session, request) == []


def test_make_pdf_helper_page_counts(session):
    assert new_request(session, make_pdf(5)).page_count == 5
