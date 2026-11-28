"""Trait 6 (pre-existing tables) for e-signature: old envelope rows survive the adoption, the lib tables arrive
beside them, and the app's own column on the request survives the lib's writes."""

from esign_util import OLD_ENVELOPES, PDF, esign_app, estimate, providers, sign_in_lib
from sqlalchemy import inspect, text

from legacy_host.db import Base
from legacy_host.esign_models import TABLES, EsignEnvelope
from legacy_host.esign_seam import envelope_status, send_for_signature, signed_pdf, void_envelope
from legacy_host.wire import legacy_envelope


def test_old_rows_are_unchanged_and_readable_through_the_host(tmp_path):
    app = esign_app(tmp_path)
    with app.state.session_factory() as session:
        rows = {r.id: r for r in session.query(EsignEnvelope).all()}
        assert len(rows) == len(OLD_ENVELOPES)
        item = legacy_envelope(rows["env-2"])
        assert item["status"] == "completed" and item["completed_at"] == "2026-10-20T12:00:00.000000"
        assert item["provider"] == "fakevendor" and item["envelope_id"] == "FV-2"
        both = providers(app, session)
        now = app.state.clock.utcnow_naive()
        assert envelope_status(session, both, rows["env-1"], now=now) == "sent"
        assert signed_pdf(session, both, rows["env-2"], now=now).startswith(b"%PDF-1.4 old")
    with app.state.session_factory() as session:  # the host service wrote nothing it should not
        raw = session.execute(text("SELECT id, status FROM esign_envelopes ORDER BY id")).all()
        assert [tuple(r) for r in raw] == [(i, s) for i, _, _, s, _ in OLD_ENVELOPES]


def test_lib_tables_arrive_beside_the_old_ones_with_the_mixin_columns(tmp_path):
    app = esign_app(tmp_path)
    names = set(inspect(app.state.engine).get_table_names())
    assert {"esign_envelopes", "estimates", "esign_requests", "esign_signers", "esign_events"} <= names
    for table in ("esign_requests", "esign_signers", "esign_events"):
        made = {c["name"] for c in inspect(app.state.engine).get_columns(table)}
        assert made == {c.name for c in Base.metadata.tables[table].columns}, table
    assert "legacy_estimate_id" in {c["name"] for c in inspect(app.state.engine).get_columns("esign_requests")}


def test_the_app_owned_column_survives_sign_complete_and_void(tmp_path):
    app = esign_app(tmp_path)
    with app.state.session_factory() as session:
        both = providers(app, session)
        now = app.state.clock.utcnow_naive()
        done = send_for_signature(session, both, "native", estimate(session, "est-7"), pdf=PDF, file_name="Estimate 7",
                                  signer_name="Pat Customer", signer_email="pat@example.com",
                                  client_user_id="cu-7", now=now, envelope_class=EsignEnvelope)
        other = send_for_signature(session, both, "native", estimate(session, "est-6"), pdf=PDF, file_name="Estimate 6",
                                   signer_name="Pat Customer", signer_email="pat@example.com",
                                   client_user_id="cu-6", now=now, envelope_class=EsignEnvelope)
        assert done.envelope_id != other.envelope_id
        sign_in_lib(app, session, done.envelope_id)
        assert signed_pdf(session, both, done, now=now).startswith(b"%PDF")
        void_envelope(session, both, other, "customer changed their mind")
        request_class = TABLES.request
        for row, status in ((done, "completed"), (other, "voided")):
            assert row.status == status
            assert session.get(request_class, row.envelope_id).legacy_estimate_id == row.estimate_id
        assert session.get(request_class, done.envelope_id).status == "completed"
    with app.state.session_factory() as session:  # and in the database, not just the session
        raw = dict(session.execute(text("SELECT id, legacy_estimate_id FROM esign_requests")).all())
        assert sorted(raw.values()) == ["est-6", "est-7"]
