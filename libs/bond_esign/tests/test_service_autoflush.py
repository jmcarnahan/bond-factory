"""Service functions must work on a session created with autoflush=False: nothing is lost by the row reload."""

from datetime import timedelta

import pytest
from conftest import CTX, NOW, Event, Request, Signer, T, at, new_request, sign_it, signers_of
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bond_esign import EsignError, build_signed_pdf, complete, decline, expire_due, verify_chain, void


@pytest.fixture
def make(engine):
    """(setup session, work-session factory, fresh-session factory); all share the one in-memory database."""
    return (
        sessionmaker(engine, expire_on_commit=False),
        sessionmaker(engine, expire_on_commit=False, autoflush=False),
    )


def reload(factory, request_id):
    s = factory()
    request = s.get(Request, request_id)
    events = list(s.execute(select(Event).where(Event.request_id == request_id).order_by(Event.seq)).scalars())
    return s, request, events


def prepare(setup, pdf, **kw):
    with setup() as s:
        request = new_request(s, pdf, **kw)
        s.commit()
        return request.id, signers_of(s, request)[0].id


def test_decline_survives_autoflush_off(make, pdf_bytes):
    setup, work = make
    rid, sid = prepare(setup, pdf_bytes)
    with work() as s:
        decline(s, T, s.get(Signer, sid), reason="no", ctx=CTX, now=at(2))
        s.commit()
    s, request, events = reload(setup, rid)
    signer = s.get(Signer, sid)
    assert (request.status, request.declined_at, signer.status, signer.decline_reason) == ("declined", at(2), "declined", "no")
    assert events[-1].kind == "declined" and verify_chain(s, T, request).ok


def test_void_survives_autoflush_off(make, pdf_bytes):
    setup, work = make
    rid, _ = prepare(setup, pdf_bytes)
    with work() as s:
        void(s, T, s.get(Request, rid), reason="mistake", ctx=CTX, now=at(2))
        s.commit()
    s, request, events = reload(setup, rid)
    assert (request.status, request.void_reason, request.voided_at) == ("voided", "mistake", at(2))
    assert events[-1].kind == "voided" and verify_chain(s, T, request).ok


def test_expire_due_survives_autoflush_off(make, pdf_bytes):
    setup, work = make
    rid, _ = prepare(setup, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    with work() as s:
        assert expire_due(s, T, now=at(6)) == 1
        s.commit()
    s, request, events = reload(setup, rid)
    assert request.status == "expired" and events[-1].kind == "expired" and verify_chain(s, T, request).ok


def test_an_expiry_hit_through_sign_survives_autoflush_off(make, pdf_bytes):
    setup, work = make
    rid, sid = prepare(setup, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    with work() as s:
        with pytest.raises(EsignError) as info:
            sign_it(s, s.get(Signer, sid), pdf_bytes, now=at(6))
        assert info.value.code == "expired"
        s.commit()
    s, request, events = reload(setup, rid)
    assert request.status == "expired" and events[-1].kind == "expired"


def test_complete_survives_autoflush_off(make, pdf_bytes):
    setup, work = make
    rid, sid = prepare(setup, pdf_bytes)
    with setup() as s:
        sign_it(s, s.get(Signer, sid), pdf_bytes)
        s.commit()
    with work() as s:
        request = s.get(Request, rid)
        signed = build_signed_pdf(s, T, request, pdf=pdf_bytes)
        complete(s, T, request, signed=signed, now=at(3))
        s.commit()
    s, request, events = reload(setup, rid)
    assert (request.status, request.signed_sha256, request.completed_at) == ("completed", signed.sha256, at(3))
    assert [e.kind for e in events][-2:] == ["document_built", "completed"] and verify_chain(s, T, request).ok


def test_sign_itself_survives_autoflush_off(make, pdf_bytes):
    setup, work = make
    rid, sid = prepare(setup, pdf_bytes)
    with work() as s:
        sign_it(s, s.get(Signer, sid), pdf_bytes)
        s.commit()
    s, request, _ = reload(setup, rid)
    assert request.status == "signed" and s.get(Signer, sid).status == "signed" and verify_chain(s, T, request).ok
