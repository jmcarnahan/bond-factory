from datetime import timedelta

from conftest import NOW, T, at, events_of, expect, kinds_of, new_request, signers_of

from bond_esign import find_signer_by_token, issue_token, sha256_hex, void


def test_token_is_random_urlsafe_and_only_its_hash_is_stored(session, pdf_bytes):
    request = new_request(session, pdf_bytes)
    signer = signers_of(session, request)[0]
    token = issue_token(session, T, signer, now=at(0))
    assert len(token) >= 43 and all(c.isalnum() or c in "-_" for c in token)  # 32 bytes, urlsafe base64
    assert signer.token_sha256 == sha256_hex(token.encode()) and token not in str(signer.__dict__)
    assert signer.token_expires_at is None
    ev = events_of(session, request)[-1]
    assert ev.kind == "token_issued" and token not in str(ev.data) and signer.token_sha256 not in str(ev.data)
    assert find_signer_by_token(session, T, token, now=at(1)) is signer


def test_issuing_again_replaces_the_earlier_token(session, pdf_bytes):
    signer = signers_of(session, new_request(session, pdf_bytes))[0]
    first = issue_token(session, T, signer, now=at(0))
    second = issue_token(session, T, signer, now=at(1))
    assert first != second
    assert find_signer_by_token(session, T, first, now=at(2)) is None
    assert find_signer_by_token(session, T, second, now=at(2)) is signer


def test_a_ttl_sets_an_expiry_that_find_respects(session, pdf_bytes):
    signer = signers_of(session, new_request(session, pdf_bytes))[0]
    token = issue_token(session, T, signer, now=at(0), ttl_seconds=3600)
    assert signer.token_expires_at == NOW + timedelta(hours=1)
    assert find_signer_by_token(session, T, token, now=at(59, 59)) is signer
    assert find_signer_by_token(session, T, token, now=at(60)) is None


def test_unknown_empty_and_look_alike_tokens_find_nothing_and_write_nothing(session, pdf_bytes):
    request = new_request(session, pdf_bytes)
    signer = signers_of(session, request)[0]
    token = issue_token(session, T, signer, now=at(0))
    n = len(events_of(session, request))
    for bad in ("", "nope", token[:-1], token + "x", token.upper(), sha256_hex(token.encode())):
        assert find_signer_by_token(session, T, bad, now=at(1)) is None
    assert len(events_of(session, request)) == n


def test_each_signer_has_their_own_token(session, pdf_bytes):
    from bond_esign import SignerSpec

    request = new_request(session, pdf_bytes, signers=[SignerSpec("A"), SignerSpec("B")])
    a, b = signers_of(session, request)
    ta, tb = issue_token(session, T, a, now=at(0)), issue_token(session, T, b, now=at(0))
    assert find_signer_by_token(session, T, ta, now=at(1)) is a and find_signer_by_token(session, T, tb, now=at(1)) is b


def test_no_token_for_an_expired_request_but_a_voided_one_still_resolves(session, pdf_bytes):
    request = new_request(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    signer = signers_of(session, request)[0]
    with expect("expired"):
        issue_token(session, T, signer, now=at(6))
    assert kinds_of(session, request) == ["created", "expired"]
    other = new_request(session, pdf_bytes)
    other_signer = signers_of(session, other)[0]
    token = issue_token(session, T, other_signer, now=at(0))
    void(session, T, other, reason="x", ctx=None, now=at(1))
    assert find_signer_by_token(session, T, token, now=at(2)) is other_signer  # the page can say "voided"
