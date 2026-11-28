import hashlib
from datetime import timedelta

from conftest import CTX, NOW, T, at, events_of, expect, kinds_of, new_request, signers_of

from bond_esign import Policy, decline, issue_code, verify_code, void


def setup(session, pdf, **kw):
    request = new_request(session, pdf, policy=Policy(**kw))
    return request, signers_of(session, request)[0]


def test_code_is_six_digits_hashed_with_the_signer_id_and_logged_without_it(session, pdf_bytes):
    request, signer = setup(session, pdf_bytes)
    code = issue_code(session, T, signer, now=at(0))
    assert len(code) == 6 and code.isdigit()
    assert signer.code_sha256 == hashlib.sha256(f"{signer.id}:{code}".encode()).hexdigest()
    assert (signer.code_sent_at, signer.code_expires_at) == (NOW, NOW + timedelta(seconds=600))
    assert (signer.code_attempts, signer.code_verified_at) == (0, None)
    sent = events_of(session, request)[-1]
    assert sent.kind == "code_sent" and code not in str(sent.data) and signer.code_sha256 not in str(sent.data)


def test_a_right_code_verifies_clears_the_hash_and_a_second_submit_is_still_true(session, pdf_bytes):
    request, signer = setup(session, pdf_bytes)
    code = issue_code(session, T, signer, now=at(0))
    assert verify_code(session, T, signer, code, ctx=CTX, now=at(1)) is True
    assert (signer.code_verified_at, signer.code_sha256) == (at(1), None)
    last = events_of(session, request)[-1]
    assert (last.kind, last.ip, last.signer_id) == ("code_verified", CTX.ip, signer.id)
    before = len(events_of(session, request))
    assert verify_code(session, T, signer, code, ctx=CTX, now=at(2)) is True  # a double submit, not an error
    assert verify_code(session, T, signer, "000000", ctx=CTX, now=at(3)) is True
    assert (len(events_of(session, request)), signer.code_verified_at, signer.code_attempts) == (before, at(1), 0)


def test_a_new_code_after_verifying_must_be_verified_again(session, pdf_bytes):
    _, signer = setup(session, pdf_bytes)
    verify_code(session, T, signer, issue_code(session, T, signer, now=at(0)), ctx=CTX, now=at(1))
    code = issue_code(session, T, signer, now=at(2))
    assert verify_code(session, T, signer, "000000" if code != "000000" else "111111", ctx=CTX, now=at(3)) is False
    assert verify_code(session, T, signer, code, ctx=CTX, now=at(4)) is True


def test_verify_without_a_code_ever_issued_is_code_invalid(session, pdf_bytes):
    _, signer = setup(session, pdf_bytes)
    with expect("code_invalid"):
        verify_code(session, T, signer, "123456", ctx=CTX, now=at(1))


def test_a_wrong_code_counts_an_attempt_and_logs_code_failed(session, pdf_bytes):
    request, signer = setup(session, pdf_bytes)
    code = issue_code(session, T, signer, now=at(0))
    wrong = "000000" if code != "000000" else "111111"
    assert verify_code(session, T, signer, wrong, ctx=CTX, now=at(1)) is False
    assert signer.code_attempts == 1 and signer.code_verified_at is None
    failed = events_of(session, request)[-1]
    assert (failed.kind, failed.data) == ("code_failed", {"reason": "wrong"})
    assert verify_code(session, T, signer, f" {code} ", ctx=CTX, now=at(2)) is True  # whitespace is forgiven


def test_the_code_expires_after_the_ttl(session, pdf_bytes):
    request, signer = setup(session, pdf_bytes, code_ttl_seconds=120)
    code = issue_code(session, T, signer, now=at(0))
    assert verify_code(session, T, signer, code, ctx=CTX, now=at(2)) is False  # exactly at expiry
    assert events_of(session, request)[-1].data == {"reason": "expired"} and signer.code_attempts == 1


def test_too_many_attempts_raises_before_comparing_even_the_right_code(session, pdf_bytes):
    request, signer = setup(session, pdf_bytes, code_max_attempts=3)
    code = issue_code(session, T, signer, now=at(0))
    wrong = "000000" if code != "000000" else "111111"
    for minute in (1, 2, 3):
        assert verify_code(session, T, signer, wrong, ctx=CTX, now=at(minute)) is False
    n = len(events_of(session, request))
    with expect("too_many_attempts"):
        verify_code(session, T, signer, code, ctx=CTX, now=at(4))  # the right code is no longer tried
    assert len(events_of(session, request)) == n and signer.code_verified_at is None
    fresh = issue_code(session, T, signer, now=at(5))  # a new code resets the count
    assert signer.code_attempts == 0 and verify_code(session, T, signer, fresh, ctx=CTX, now=at(6)) is True


def test_resending_inside_the_gap_is_code_too_soon_and_after_it_replaces_the_code(session, pdf_bytes):
    request, signer = setup(session, pdf_bytes, code_resend_seconds=30)
    first = issue_code(session, T, signer, now=at(0))
    with expect("code_too_soon"):
        issue_code(session, T, signer, now=at(0, 29))
    assert kinds_of(session, request).count("code_sent") == 1
    second = issue_code(session, T, signer, now=at(0, 30))
    assert signer.code_sha256 == hashlib.sha256(f"{signer.id}:{second}".encode()).hexdigest()
    if first != second:
        assert verify_code(session, T, signer, first, ctx=CTX, now=at(1)) is False  # the old code is dead


def test_a_new_code_resets_a_verified_signer(session, pdf_bytes):
    _, signer = setup(session, pdf_bytes)
    verify_code(session, T, signer, issue_code(session, T, signer, now=at(0)), ctx=CTX, now=at(1))
    issue_code(session, T, signer, now=at(2))
    assert signer.code_verified_at is None


def test_codes_need_an_open_request_and_a_pending_signer(session, pdf_bytes):
    request = new_request(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    signer = signers_of(session, request)[0]
    with expect("expired"):
        issue_code(session, T, signer, now=at(6))
    with expect("expired"):
        verify_code(session, T, signer, "123456", ctx=CTX, now=at(7))
    other = new_request(session, pdf_bytes)
    other_signer = signers_of(session, other)[0]
    code = issue_code(session, T, other_signer, now=at(0))
    void(session, T, other, reason="x", ctx=CTX, now=at(1))
    with expect("not_open"):
        verify_code(session, T, other_signer, code, ctx=CTX, now=at(2))
    third = new_request(session, pdf_bytes)
    third_signer = signers_of(session, third)[0]
    decline(session, T, third_signer, reason=None, ctx=CTX, now=at(1))
    with expect("not_open"):
        issue_code(session, T, third_signer, now=at(2))
