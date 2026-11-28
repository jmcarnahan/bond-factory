"""expire_if_due re-checks under the row lock: it must not overwrite what another transaction just committed."""

from datetime import timedelta

from conftest import NOW, Request, T, at, events_of, kinds_of, new_request, sign_it, signers_of
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from bond_esign import verify_chain
from bond_esign.lifecycle import expire_if_due


def test_expire_if_due_is_a_noop_when_the_reloaded_status_is_no_longer_open(engine, pdf_bytes):
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as mine, factory() as other:
        request = new_request(mine, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
        mine.commit()
        stale = mine.get(Request, request.id)
        assert stale.status == "open"  # loaded, and now out of date
        other.execute(update(Request).where(Request.id == request.id).values(status="signed"))
        other.commit()
        assert expire_if_due(mine, T, stale, at(10)) is False
        assert stale.status == "signed"
        assert "expired" not in kinds_of(mine, stale)


def test_expire_if_due_twice_writes_one_event(session, pdf_bytes):
    request = new_request(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    assert expire_if_due(session, T, request, at(10)) is True
    assert expire_if_due(session, T, request, at(11)) is False
    assert kinds_of(session, request).count("expired") == 1 and verify_chain(session, T, request).ok


def test_a_signed_request_is_never_flipped_to_expired(session, pdf_bytes):
    request = new_request(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    sign_it(session, signers_of(session, request)[0], pdf_bytes, now=at(1))
    assert expire_if_due(session, T, request, at(10)) is False
    assert request.status == "signed" and events_of(session, request)[-1].kind == "signed"
