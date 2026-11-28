"""Shared helpers for the e-signature traits: an adopted database with old envelope rows, and both providers."""

from pathlib import Path

import bond_esign as be
from legacy_db import legacy_app
from sqlalchemy import select, text

from legacy_host.esign_fake_vendor import FakeVendorProvider
from legacy_host.esign_models import CONSENT, TABLES, Estimate
from legacy_host.esign_native import NativeProvider

PDF = (Path(__file__).resolve().parents[3] / "fixtures" / "esign" / "weasy_acceptance.pdf").read_bytes()
OLD_ENVELOPES = (  # (id, estimate, envelope_id, status, completed_at)
    ("env-1", "est-1", "FV-1", "sent", None),
    ("env-2", "est-2", "FV-2", "completed", "2026-10-20 12:00:00"),
    ("env-3", "est-3", "FV-3", "declined", None),
    ("env-4", "est-4", "FV-4", "voided", None),
    ("env-5", "est-5", "FV-5", "expired", None),
    ("env-6", "est-6", "FV-6", "delivered", None),
)


def old_esign_rows(connection) -> None:
    for n in range(1, 8):
        connection.execute(text("INSERT INTO estimates (id, title, total) VALUES (:id, :title, :total)"),
                           {"id": f"est-{n}", "title": f"Roof estimate {n}", "total": 1000 * n})
    for row_id, estimate, envelope_id, status, completed in OLD_ENVELOPES:
        connection.execute(text(
            "INSERT INTO esign_envelopes (id, estimate_id, provider, envelope_id, status, signer_name, signer_email, "
            "client_user_id, sent_at, completed_at) VALUES (:id, :est, 'fakevendor', :eid, :status, 'Old Customer', "
            "'old.customer@example.com', 'cu-1', '2026-10-19 09:00:00', :completed)"),
            {"id": row_id, "est": estimate, "eid": envelope_id, "status": status, "completed": completed})


def esign_app(tmp_path, fill=old_esign_rows):
    return legacy_app(tmp_path / "e.db", fill)


def providers(app, session):
    """Both providers over one session: the vendor stand-in (it knows the old rows) and the native adapter."""
    vendor = FakeVendorProvider()
    for row_id, _, envelope_id, status, _ in OLD_ENVELOPES:
        vendor.remember(envelope_id, status)
    native = NativeProvider(session, TABLES, CONSENT, app.state.clock.utcnow_naive, app.state.esign_store)
    return {"fakevendor": vendor, "native": native}


def estimate(session, estimate_id="est-7") -> Estimate:
    return session.get(Estimate, estimate_id)


def signer_of(session, envelope_id):
    return session.execute(select(TABLES.signer).where(TABLES.signer.request_id == envelope_id)).scalars().one()


def sign_in_lib(app, session, envelope_id, name="Pat Customer"):
    """The signer signs (what the page does), straight through the lib."""
    signer = signer_of(session, envelope_id)
    be.sign(session, TABLES, signer, pdf=PDF, consent_version=CONSENT.version, consent_accepted=True,
            typed_name=name, drawn_png=None, ctx=None, now=app.state.clock.utcnow_naive())
    session.commit()
