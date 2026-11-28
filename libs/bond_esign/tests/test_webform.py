import base64
import re
from dataclasses import replace

import pytest

from bond_esign import errors
from bond_esign.errors import EsignError
from bond_esign.types import Consent, SigningView
from bond_esign.webform import (
    PanelLabels,
    asset_names,
    asset_path,
    asset_tags,
    parse_submission,
    render_panel,
)

XSS = '"><script>alert(1)</script>'
ATTR = "' onload='x"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def attrs_outside_quotes(out: str) -> str:
    """The tag interiors with quoted attribute values removed: what is left is attribute names only."""
    return " ".join(re.findall(r"<[^>]*>", re.sub(r'="[^"]*"', "", out)))


def make_view(**kw) -> SigningView:
    base = {
        "request_status": "sent", "signer_status": "pending", "can_sign": True, "reason": None,
        "consent": Consent(version="v1", language="en", text="Line one.\n\nLine two."),
        "needs_code": False, "code_verified": False, "allow_typed": True, "allow_drawn": True,
        "signer_name": "Pat Example", "title": "Service agreement",
    }  # fmt: skip
    base.update(kw)
    return SigningView(**base)


def data_url(raw: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def test_fields_and_order():
    out = render_panel(make_view(), action_url="/sign/abc", hidden={"csrf": "t0k"})
    assert '<form class="bond-esign" method="post" action="/sign/abc" data-bond-esign' in out
    for name in ("csrf", "consent_version", "mode", "drawn_png", "consent_accepted", "typed_name"):
        assert f'name="{name}"' in out
    assert out.index('name="csrf"') < out.index('name="consent_version"') < out.index('name="mode"')
    assert out.index('name="drawn_png"') < out.index('name="consent_accepted"') < out.index('name="typed_name"')
    assert 'name="mode" value="typed"' in out
    assert 'name="typed_name" id="bond-esign-name" autocomplete="name" maxlength="120" value=""' in out
    assert '<p>Line one.</p><p>Line two.</p>' in out
    assert 'role="tablist"' in out and out.count('role="tab"') == 2
    assert "<canvas" in out and 'role="alert"' in out and "<noscript>" in out
    assert re.search(r'<button type="submit"[^>]*>Sign and accept</button>', out)
    assert "disabled" not in out
    # tabs and draw area are hidden until the script runs
    assert re.search(r'role="tablist"[^>]*\bhidden>', out)
    assert re.search(r'id="bond-esign-panel-drawn" role="tabpanel" hidden>', out)


def test_hostile_values_are_escaped():
    consent = Consent(version=XSS, language="en", text=XSS + "\n" + ATTR)
    labels = PanelLabels(heading=XSS, submit=XSS, name_label=ATTR, consent_label=XSS, clear=XSS)
    view = make_view(signer_name=XSS, title=ATTR + XSS, consent=consent)
    out = render_panel(
        view, action_url=XSS + ATTR, labels=labels, hidden={XSS: ATTR + XSS}, error=XSS + ATTR, id_prefix=XSS
    )
    assert "<script" not in out and "alert(1)</script" not in out
    assert "' onload='x" not in out
    assert "&lt;script&gt;" in out and "&#x27; onload=&#x27;x" in out
    assert not re.search(r"\son\w+=", attrs_outside_quotes(out))


def test_strict_csp_markup():
    out = render_panel(make_view(), action_url="/s")
    for bad in ("<dialog", "popover", "<script", "<style", "style="):
        assert bad not in out
    assert not re.search(r"\son\w+\s*=", attrs_outside_quotes(out))
    assert "novalidate" not in out


def test_two_panels_share_a_page():
    a = render_panel(make_view(), action_url="/s", id_prefix="p1")
    assert 'id="p1-consent"' in a and 'for="p1-consent"' in a and 'id="bond-esign-consent"' not in a


@pytest.mark.parametrize(
    ("kw", "text"),
    [
        ({"can_sign": False, "signer_status": "signed"}, "Thank you. This document is signed."),
        ({"can_sign": False, "reason": errors.EXPIRED}, "expired"),
        ({"can_sign": False, "reason": errors.NOT_OPEN}, "not ready"),
        ({"can_sign": False, "reason": errors.ALREADY_COMPLETED}, "cannot be signed"),
        ({"needs_code": True, "code_verified": False}, "code we sent"),
    ],
)
def test_closed_views_have_no_form(kw, text):
    out = render_panel(make_view(**kw), action_url="/s")
    assert "<form" not in out and "<input" not in out
    assert 'class="bond-esign bond-esign--closed"' in out and text in out


def test_verified_code_shows_form():
    assert "<form" in render_panel(make_view(needs_code=True, code_verified=True), action_url="/s")


def test_typed_only():
    out = render_panel(make_view(allow_drawn=False), action_url="/s")
    assert "<canvas" not in out and "tablist" not in out and 'name="mode" value="typed"' in out
    assert "required" in out


def test_drawn_only():
    out = render_panel(make_view(allow_typed=False), action_url="/s")
    assert "<canvas" in out and "tablist" not in out and 'name="mode" value="drawn"' in out
    assert "bond-esign__preview" not in out


def test_noscript_hint_matches_what_a_no_js_signer_can_do():
    both = render_panel(make_view(), action_url="/s")
    assert "typing your full name" in both and "JavaScript is needed" not in both
    drawn = render_panel(make_view(allow_typed=False), action_url="/s")
    assert "JavaScript is needed to draw your signature. Please turn it on and reload this page." in drawn
    assert "typing your full name" not in drawn
    spanish = render_panel(make_view(allow_typed=False), action_url="/s", labels=PanelLabels.spanish())
    assert "Se necesita JavaScript para dibujar su firma" in spanish and "escribiendo" not in spanish


def test_neither_mode_is_closed():
    out = render_panel(make_view(allow_typed=False, allow_drawn=False), action_url="/s")
    assert "<form" not in out


def test_spanish_labels():
    out = render_panel(make_view(), action_url="/s", labels=PanelLabels.spanish())
    assert "Firmar y aceptar" in out and "Su nombre completo" in out and "Dibujar" in out
    assert "Firmando como Pat Example" in out
    closed = render_panel(make_view(can_sign=False, signer_status="signed"), action_url="/s",
                          labels=PanelLabels.spanish())  # fmt: skip
    assert "Gracias" in closed


def test_error_line_text():
    out = render_panel(make_view(), action_url="/s", error="Try again & retry")
    assert 'role="alert" id="bond-esign-error">Try again &amp; retry</p>' in out


def test_asset_tags_order_and_escape():
    tags = asset_tags('/static/"x/')
    assert tags.index("signature_pad") < tags.index("bond-esign.js")
    assert tags.count("<script defer") == 2 and 'href="/static/&quot;x/bond-esign.css"' in tags


def test_asset_path_rules():
    assert asset_names() == tuple(sorted(asset_names())) and len(asset_names()) == 4
    assert "README.md" not in asset_names()
    for name in asset_names():
        assert asset_path(name).is_file()
    for bad in ("../x", "/etc/passwd", "README.md", "web/bond-esign.js", "", "..", "bond-esign.js/"):
        with pytest.raises(ValueError):
            asset_path(bad)


def good(**kw):
    form = {"consent_version": "v1", "consent_accepted": "1", "mode": "drawn", "drawn_png": data_url(PNG)}
    form.update(kw)
    return form


def test_parse_happy_drawn():
    s = parse_submission(good(typed_name="  Pat Example "), max_signature_bytes=1000)
    assert (s.consent_version, s.consent_accepted, s.typed_name, s.drawn_png) == ("v1", True, "Pat Example", PNG)


@pytest.mark.parametrize(("val", "ok"), [("1", True), ("on", True), ("true", True), ("0", False), ("yes", False), ("", False)])
def test_consent_values(val, ok):
    assert parse_submission(good(consent_accepted=val), max_signature_bytes=1000).consent_accepted is ok


def test_missing_fields_do_not_raise():
    s = parse_submission({}, max_signature_bytes=1000)
    assert s == replace(s, consent_version="", consent_accepted=False, typed_name=None, drawn_png=None)
    assert parse_submission({"typed_name": "   "}, max_signature_bytes=10).typed_name is None


def test_typed_mode_ignores_drawn_png():
    s = parse_submission(good(mode="typed", drawn_png="garbage"), max_signature_bytes=1000)
    assert s.drawn_png is None


def test_drawn_empty_is_none():
    assert parse_submission(good(drawn_png=""), max_signature_bytes=1000).drawn_png is None


def test_oversize_rejected_before_decode():
    huge = "data:image/png;base64," + "!" * 5000  # invalid base64: only the size check can explain the error
    with pytest.raises(EsignError) as exc:
        parse_submission(good(drawn_png=huge), max_signature_bytes=1000)
    assert exc.value.code == errors.SIGNATURE_INVALID and "too large" in exc.value.message


def test_decoded_size_cap():
    with pytest.raises(EsignError, match="too large"):
        parse_submission(good(drawn_png=data_url(PNG + b"0" * 100)), max_signature_bytes=60)


@pytest.mark.parametrize(
    "raw",
    [
        "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode(),
        "data:image/png;base64," + base64.b64encode(b"\xff\xd8\xff\xe0JFIF").decode(),
        "data:image/png;base64,!!!notbase64",
        "data:image/png;base64,",
        "data:image/png;charset=x;base64," + base64.b64encode(PNG).decode(),
        "http://example.com/x.png",
    ],
)
def test_bad_drawn_rejected(raw):
    with pytest.raises(EsignError) as exc:
        parse_submission(good(drawn_png=raw), max_signature_bytes=1000)
    assert exc.value.code == errors.SIGNATURE_INVALID
