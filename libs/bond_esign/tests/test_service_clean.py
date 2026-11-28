"""Stored text is cleaned (no NUL or control characters, bounded) and what is hashed is what is stored."""

import pytest
from conftest import T, at, events_of, expect, new_request, sig_png, sign_it, signers_of

from bond_esign import RequestContext, SignerSpec, decline, evidence, verify_chain, void
from bond_esign._rows import clean


def one(session, pdf, **kw):
    request = new_request(session, pdf, **kw)
    return request, signers_of(session, request)[0]


def test_clean_strips_controls_but_keeps_newline_and_tab_and_truncates():
    assert clean("a\x00b\x01c\x7fd\te\nf\rg", 100) == "abcd\te\nfg"
    assert clean("x" * 10, 4) == "xxxx" and clean(None, 5) is None


def test_drawn_signature_with_a_name_outside_cp1252_is_accepted(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes, typed_name="Nguyễn Văn An", drawn_png=sig_png())
    assert (signer.signature_kind, signer.typed_name) == ("drawn", "Nguyễn Văn An")


def test_drawn_name_is_still_checked_for_length_and_printable_characters(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    with expect("signature_invalid"):
        sign_it(session, signer, pdf_bytes, typed_name="N" * 121, drawn_png=sig_png())
    with expect("name_not_renderable"):
        sign_it(session, signer, pdf_bytes, typed_name="Pat\u200b Example", drawn_png=sig_png())
    assert signer.status == "pending"


def test_nul_in_user_agent_actor_and_reasons_is_never_stored_and_the_chain_verifies(session, pdf_bytes):
    ctx = RequestContext(ip="203.0.113.7\x00", user_agent="Agent\x00/1\x07.0", actor="staff\x00-1")
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes, ctx=ctx, typed_name="Pat\x00 Example")
    assert signer.typed_name == "Pat Example" and signer.user_agent == "Agent/1.0" and signer.ip == "203.0.113.7"
    other, other_signer = one(session, pdf_bytes)
    decline(session, T, other_signer, reason="no\x00pe", ctx=ctx, now=at(2))
    third, _ = one(session, pdf_bytes)
    void(session, T, third, reason="oops\x00", ctx=ctx, now=at(2))
    assert (other_signer.decline_reason, third.void_reason) == ("nope", "oops")
    for r in (request, other, third):
        assert verify_chain(session, T, r).ok
        for e in events_of(session, r):
            assert "\x00" not in f"{e.ip}{e.user_agent}{e.actor}{e.data}"
    assert "\x00" not in str(evidence(session, T, request))
    assert events_of(session, other)[-1].user_agent == "Agent/1.0" and events_of(session, other)[-1].actor == "staff-1"


def test_over_long_values_are_truncated(session, pdf_bytes):
    ctx = RequestContext(ip="1" * 100, user_agent="U" * 5000, actor="A" * 500)
    request, signer = one(session, pdf_bytes)
    decline(session, T, signer, reason="R" * 5000, ctx=ctx, now=at(2))
    last = events_of(session, request)[-1]
    assert (len(last.ip), len(last.user_agent), len(last.actor), len(last.data["reason"])) == (64, 1000, 200, 2000)
    assert len(signer.decline_reason) == 2000 and verify_chain(session, T, request).ok


def test_create_request_cleans_and_bounds_titles_and_signer_fields(session, pdf_bytes):
    spec = SignerSpec(name="Pat\x00" + "N" * 600, email="pat\x00@example.com", role="Owner\x00", key="k\x00" * 700)
    request = new_request(session, pdf_bytes, signers=[spec], title="T\x00" + "x" * 600)
    signer = signers_of(session, request)[0]
    assert len(request.title) == 500 and "\x00" not in request.title
    assert (len(signer.name), signer.email, signer.role, len(signer.key)) == (500, "pat@example.com", "Owner", 500)
    assert "\x00" not in signer.name + signer.key


def test_an_all_control_typed_name_is_signature_required(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    with expect("signature_required"):
        sign_it(session, signer, pdf_bytes, typed_name="\x00\x01\x02")
    assert signer.status == "pending"


@pytest.mark.parametrize("bad", ["\x00", "\x1b"])
def test_view_events_clean_the_context_too(session, pdf_bytes, bad):
    from bond_esign import signing_view

    request, signer = one(session, pdf_bytes)
    signing_view(session, T, signer, ctx=RequestContext(user_agent=f"UA{bad}x"), now=at(1))
    assert events_of(session, request)[-1].user_agent == "UAx"
