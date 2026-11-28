"""Decline block of the signing panel, the reason parser and the declined notice."""

import pathlib

from test_webform import make_view

from bond_esign.webform import PanelLabels, asset_path, parse_decline, render_panel

# render_panel(make_view(), action_url="/sign/abc", hidden={"csrf": "t0k"}, error="Oops"), captured before
# decline_url existed (no trailing newline).
BASELINE = (pathlib.Path(__file__).parent / "panel_open_before_decline.html").read_text(encoding="utf-8")

KW = {"action_url": "/sign/abc", "hidden": {"csrf": "t0k"}, "error": "Oops"}
EN_BLOCK = (
    '<details class="bond-esign__decline"><summary>Decline to sign</summary>'
    '<form method="post" action="/decline/abc" class="bond-esign__decline-form">'
    '<label for="bond-esign-decline-reason">Reason (optional)</label>'
    '<textarea id="bond-esign-decline-reason" name="bond_esign_decline_reason" maxlength="2000" rows="3">'
    "</textarea>"
    '<button type="submit" class="bond-esign__decline-submit">Decline</button></form></details>'
)


def test_without_decline_url_the_output_is_unchanged():
    assert render_panel(make_view(), **KW) == BASELINE
    assert render_panel(make_view(), decline_url=None, **KW) == BASELINE


def test_decline_block_follows_the_sign_form_and_never_nests():
    out = render_panel(make_view(), decline_url="/decline/abc", **KW)
    assert out == BASELINE + "\n" + EN_BLOCK
    assert out.index("</form>") < out.index("<details")
    assert out.count("<form") == 2 and out.count("</form>") == 2
    assert "<script" not in out and "confirm" not in out and "dialog" not in out


def test_decline_texts_are_escaped_and_translated():
    labels = PanelLabels(decline_summary='<b>"x"</b>')
    out = render_panel(make_view(), decline_url='/d?a="1"&b=2', labels=labels, **KW)
    assert "&lt;b&gt;&quot;x&quot;&lt;/b&gt;" in out
    assert 'action="/d?a=&quot;1&quot;&amp;b=2"' in out
    es = render_panel(make_view(), decline_url="/d", labels=PanelLabels.spanish(), **KW)
    assert "Rechazar la firma" in es and "Motivo (opcional)" in es and ">Rechazar</button>" in es


def test_decline_block_only_on_the_open_panel():
    for kw in (
        {"can_sign": False, "signer_status": "signed"},
        {"can_sign": False, "reason": "expired"},
        {"needs_code": True},
    ):
        assert "decline" not in render_panel(make_view(**kw), decline_url="/d", **KW)


def test_declined_signer_sees_the_declined_message():
    view = make_view(can_sign=False, signer_status="declined", request_status="declined", reason="not_open")
    out = render_panel(view, decline_url="/d", **KW)
    assert "You declined to sign this document. Nothing was signed." in out and "<form" not in out
    assert "Usted rechazó firmar" in render_panel(view, labels=PanelLabels.spanish(), **KW)
    other = make_view(can_sign=False, signer_status="pending", request_status="voided", reason="not_open")
    assert "declined" not in render_panel(other, **KW)


def test_parse_decline():
    assert parse_decline({"bond_esign_decline_reason": "  Wrong \x00price\x07\n here  "}) == "Wrong price\n here"
    assert parse_decline({"bond_esign_decline_reason": "x" * 3000}) == "x" * 2000
    assert parse_decline({"bond_esign_decline_reason": "   \x00 "}) is None
    assert parse_decline({}) is None
    assert parse_decline({"bond_esign_decline_reason": 5}) is None


def test_the_script_does_not_pick_up_the_decline_form():
    js = asset_path("bond-esign.js").read_text(encoding="utf-8")
    assert "form[data-bond-esign]" in js and "decline" not in js


def test_labels_have_all_decline_fields_in_both_languages():
    for labels in (PanelLabels(), PanelLabels.spanish()):
        for field in ("decline_summary", "decline_reason_label", "decline_submit", "declined_message"):
            assert getattr(labels, field).strip()
    assert "ó" in PanelLabels.spanish().declined_message
