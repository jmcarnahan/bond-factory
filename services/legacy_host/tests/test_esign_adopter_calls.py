"""The native provider called the way an existing app's own code calls its seam (status, then fetch; take-back; label)."""

import io
from datetime import timedelta

import bond_esign as be
import pytest
from esign_util import PDF, esign_app, estimate, providers, signer_of
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import text

from legacy_host.esign_models import CONSENT, TABLES, EsignEnvelope
from legacy_host.esign_seam import (
    EsignError,
    complete_envelope,
    send_for_signature,
    signing_link,
    take_back,
)

FORM = {"content-type": "application/x-www-form-urlencoded"}


def send(session, both, provider, est, now, pdf=PDF):
    return send_for_signature(session, both, provider, est, pdf=pdf, file_name="Estimate", signer_name="Pat Customer",
                              signer_email="pat@example.com", client_user_id="cu-7", now=now, envelope_class=EsignEnvelope)


def post_sign(client, link):
    form = f"consent_version={CONSENT.version}&consent_accepted=1&mode=typed&typed_name=Pat+Customer"
    return client.post(link, content=form, headers=FORM, follow_redirects=False)


def labelled_pdf(label: str) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(612, 792), invariant=1)
    pdf.drawString(72, 300, label)
    pdf.line(72 + 150, 298, 500, 298)
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def test_the_whole_flow_through_complete_envelope_with_both_providers(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", estimate(session), now)
        with pytest.raises(RuntimeError, match="trying again later"):  # nobody has signed yet
            complete_envelope(session, both, row, now)
        link = signing_link(session, both, row, "http://testserver/estimates/est-7/sign")
        done = post_sign(client, link)
        assert done.status_code == 303 and app.state.esign_jobs == [row.envelope_id]
        assert both["native"].status(row.envelope_id) == "completed" and row.status == "sent"
        complete_envelope(session, both, row, now)  # first call succeeds: status says completed, PDF fetched
        assert row.status == "completed" and row.completed_at == now
        assert session.get(TABLES.request, row.envelope_id).status == "completed"
        assert b"%PDF" in app.state.esign_store.get(f"esign/{row.envelope_id}/signed.pdf")
        assert complete_envelope(session, both, row, now) is None  # a second call is a skip

        old = send(session, both, "fakevendor", estimate(session, "est-6"), now)
        with pytest.raises(RuntimeError, match="trying again later"):
            complete_envelope(session, both, old, now)
        both["fakevendor"].set_status(old.envelope_id, "completed")  # the webhook
        assert complete_envelope(session, both, old, now).endswith(b"%vendor-signed") and old.status == "completed"


def test_the_take_back_race_after_signing_before_the_job(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", estimate(session), now)
        post_sign(client, signing_link(session, both, row, "http://testserver/estimates/est-7/sign"))
        with pytest.raises(EsignError) as refused:
            take_back(session, both, "est-7", "customer changed their mind")
        assert refused.value.code == "ALREADY_SIGNED" and row.status == "sent"
        assert session.get(TABLES.request, row.envelope_id).status == "signed"
        assert client.get("/estimates/est-7/envelopes").json()[0]["status"] == "sent"  # not completed ahead of the job
        complete_envelope(session, both, row, now)
        assert row.status == "completed"


def test_take_back_voids_an_open_envelope_and_the_page_shows_no_form(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", estimate(session), now)
        link = signing_link(session, both, row, "http://testserver/estimates/est-7/sign")
        assert "typed_name" in client.get(link).text
        take_back(session, both, "est-7", "sent in error")
        assert row.status == "voided" and session.get(TABLES.request, row.envelope_id).status == "voided"
    page = client.get(link)
    assert page.status_code == 200 and "typed_name" not in page.text and "<form" not in page.text


def test_the_anchor_label_comes_from_the_estimate_and_defaults(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        owner = labelled_pdf("Approved by (owner)")
        session.execute(text("UPDATE estimates SET customer_line = 'Approved by (owner)' WHERE id = 'est-7'"))
        session.commit()
        row = send(session, both, "native", estimate(session), now, pdf=owner)
        placement = signer_of(session, row.envelope_id).placement
        expected = be.find_anchor(owner, be.AnchorRule("Approved by (owner)"))
        assert expected is not None and placement["page"] == 1
        assert placement["y"] == pytest.approx(expected.y) and placement["x"] == pytest.approx(expected.x)
        plain = send(session, both, "native", estimate(session, "est-5"), now)  # NULL column: "Accepted by (customer)"
        default = be.find_anchor(PDF, be.AnchorRule("Accepted by (customer)"))
        assert default is not None and signer_of(session, plain.envelope_id).placement["y"] == pytest.approx(default.y)


def test_valid_until_in_the_future_becomes_expires_at(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    later, past = now + timedelta(days=30), now - timedelta(days=1)
    with app.state.session_factory() as session:
        both = providers(app, session)
        estimate(session).valid_until, estimate(session, "est-6").valid_until = later, past
        session.commit()
        kept = send(session, both, "native", estimate(session), now)
        assert session.get(TABLES.request, kept.envelope_id).expires_at == later
        stale = send(session, both, "native", estimate(session, "est-6"), now)  # a past date is not passed on
        assert session.get(TABLES.request, stale.envelope_id).expires_at is None
        none = send(session, both, "native", estimate(session, "est-5"), now)
        assert session.get(TABLES.request, none.envelope_id).expires_at is None


def test_the_sign_post_redirects_with_the_marker_and_the_page_waits_for_the_job(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", estimate(session), now)
        link = signing_link(session, both, row, "http://testserver/estimates/est-7/sign")
        done = post_sign(client, link)
        target = done.headers["location"]
        assert done.status_code == 303 and "event=signing_complete" in target and "t=" in target
        waiting = client.get(target)
        assert "recording your signature" in waiting.text and "<form" not in waiting.text
        complete_envelope(session, both, row, now)
        assert "recording your signature" not in client.get(target).text
