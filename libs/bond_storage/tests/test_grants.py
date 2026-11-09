from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from conftest import Grant, load_document

from bond_storage import (
    MAX_TOKEN_LEN,
    GrantUnavailable,
    claim,
    has_live_link,
    hash_token,
    mint,
    resolve,
    revoke,
    revoke_for_owner,
)
from bond_storage.grants import utcnow_naive

T0 = datetime(2030, 1, 1, 12, 0)


def make(session, doc, **kw):
    kw.setdefault("user_id", "u1")
    grant, raw = mint(session, doc, grant_model=Grant, **kw)
    session.commit()
    return grant, raw


def look(session, raw, **kw):
    return resolve(session, raw, grant_model=Grant, document_loader=load_document, **kw)


def test_mint_resolve_claim_once(session, doc):
    grant, raw = make(session, doc, max_downloads=1)
    found, found_doc = look(session, raw)
    assert found.id == grant.id and found_doc.id == "d1"
    assert (grant.purpose, grant.owner_type, grant.owner_id, grant.created_by) == ("share", "estimate", "e1", "u1")
    assert claim(session, grant, "10.0.0.1") is True
    assert grant.download_count == 1 and grant.last_ip == "10.0.0.1" and grant.last_downloaded_at is not None
    assert claim(session, grant, "10.0.0.2") is False
    assert grant.download_count == 1 and grant.last_ip == "10.0.0.1"
    with pytest.raises(GrantUnavailable):
        look(session, raw)


def test_two_resolvers_only_one_claim_wins(factory, session, doc):
    grant, raw = make(session, doc, max_downloads=1)
    with factory() as other:
        other_grant, _ = look(other, raw)
        assert claim(session, grant) is True
        assert claim(other, other_grant) is False


def test_concurrent_claims_increment_in_sql_not_in_python(factory, session, doc):
    grant, raw = make(session, doc, max_downloads=None)
    with factory() as other:
        other_grant, _ = look(other, raw)  # both sessions hold download_count == 0
        assert claim(session, grant) is True
        assert claim(other, other_grant) is True
    with factory() as fresh:
        assert fresh.get(Grant, grant.id).download_count == 2


def test_unlimited_downloads_keep_counting(session, doc):
    grant, _ = make(session, doc, max_downloads=None)
    assert all(claim(session, grant) for _ in range(25)) and grant.download_count == 25


def test_expired_and_ttl_seconds(session, doc):
    grant, raw = make(session, doc, now=lambda: T0)
    assert grant.expires_at == T0 + timedelta(days=30)
    assert look(session, raw, now=lambda: T0 + timedelta(days=29))[0].id == grant.id
    with pytest.raises(GrantUnavailable):
        look(session, raw, now=lambda: T0 + timedelta(days=30))
    assert claim(session, grant, now=lambda: T0 + timedelta(days=31)) is False
    short, _ = make(session, doc, now=lambda: T0, ttl_days=9, ttl_seconds=90)
    assert short.expires_at == T0 + timedelta(seconds=90)


def test_revoked_and_revoke_for_owner(session, doc):
    g1, r1 = make(session, doc)
    g2, r2 = make(session, doc, purpose="view")
    assert has_live_link(session, "estimate", "e1", grant_model=Grant)
    assert revoke_for_owner(session, "estimate", "e1", grant_model=Grant, purpose="view") == 1
    with pytest.raises(GrantUnavailable):
        look(session, r2)
    assert look(session, r1)[0].id == g1.id
    revoke(g1)
    session.commit()
    with pytest.raises(GrantUnavailable):
        look(session, r1)
    assert claim(session, g1) is False
    assert not has_live_link(session, "estimate", "e1", grant_model=Grant)
    assert revoke_for_owner(session, "estimate", "nobody", grant_model=Grant) == 0
    assert g2.revoked_at is not None


def test_exhausted(session, doc):
    grant, raw = make(session, doc, max_downloads=2)
    assert claim(session, grant) and claim(session, grant)
    with pytest.raises(GrantUnavailable):
        look(session, raw)
    assert not has_live_link(session, "estimate", "e1", grant_model=Grant)


@pytest.mark.parametrize("raw", ["", "   ", "unknown-token", "x" * (MAX_TOKEN_LEN + 1), None])
def test_unknown_empty_and_overlong_tokens(session, doc, raw):
    make(session, doc)
    with pytest.raises(GrantUnavailable):
        look(session, raw)


def test_overlong_token_is_refused_before_hashing(session, doc, monkeypatch):
    import bond_storage.grants as g

    monkeypatch.setattr(g, "hash_token", lambda *_: pytest.fail("hashed an overlong token"))
    with pytest.raises(GrantUnavailable):
        look(session, "x" * 129)


def test_document_gone(session, doc):
    _, raw = make(session, doc)
    with pytest.raises(GrantUnavailable):
        resolve(session, raw, grant_model=Grant, document_loader=lambda s, i: None)


def test_only_the_hash_is_stored(session, doc):
    grant, raw = make(session, doc)
    assert len(raw) >= 43 and grant.token_hash == hash_token(raw) and len(grant.token_hash) == 64
    for row in session.execute(sa.text("select * from download_grants")).all():
        assert raw not in [str(v) for v in row]
    assert raw != grant.token_hash and mint(session, doc, grant_model=Grant, user_id=None)[1] != raw


def test_owner_defaults_and_overrides(session, doc):
    grant, _ = make(session, doc, owner_type="invoice", owner_id="i9")
    assert (grant.owner_type, grant.owner_id) == ("invoice", "i9")


def test_default_clock_is_naive_utc():
    assert utcnow_naive().tzinfo is None
    assert abs((utcnow_naive() - datetime.now(UTC).replace(tzinfo=None)).total_seconds()) < 5
