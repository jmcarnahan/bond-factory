"""The legacy wire for e-signature: the host's status words and error code come out of the adapter."""

import bond_esign as be
import pytest
from esign_util import PDF, esign_app, estimate, providers, sign_in_lib, signer_of

from legacy_host.esign_models import TABLES, EsignEnvelope
from legacy_host.esign_seam import CANNOT_VOID, STATUSES, EsignError, send_for_signature, void_envelope
from legacy_host.wire import legacy_envelope


def send(session, both, provider, estimate_id, now):
    return send_for_signature(session, both, provider, estimate(session, estimate_id), pdf=PDF, file_name="Estimate",
                              signer_name="Pat Customer", signer_email="pat@example.com", client_user_id="cu-1",
                              now=now, envelope_class=EsignEnvelope)


def test_every_lib_status_comes_out_as_a_host_status_word(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        native = both["native"]
        env = {n: send(session, both, "native", f"est-{n}", now).envelope_id for n in (1, 2, 3, 4, 5, 6)}
        assert native.status(env[1]) == "sent"  # open
        view_signer = signer_of(session, env[1])
        be.signing_view(session, TABLES, view_signer, ctx=None, now=now)
        assert native.status(env[1]) == "delivered"  # open, and the signer has viewed
        sign_in_lib(app, session, env[2])
        assert session.get(TABLES.request, env[2]).status == "signed" and native.status(env[2]) == "delivered"
        native.fetch_signed_pdf(env[2])
        assert native.status(env[2]) == "completed"
        be.decline(session, TABLES, signer_of(session, env[3]), reason="no thanks", ctx=None, now=now)
        assert native.status(env[3]) == "declined"
        native.void(env[4], "mistake")
        assert native.status(env[4]) == "voided"
        late = session.get(TABLES.request, env[5])
        late.expires_at = now.replace(year=now.year - 1)
        be.expire_due(session, TABLES, now=now)
        assert native.status(env[5]) == "expired"
        got = {native.status(e) for e in env.values()}
        assert got <= set(STATUSES) and got == {"delivered", "completed", "declined", "voided", "expired", "sent"}


def test_void_after_completion_is_the_hosts_own_error_with_its_code(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", "est-7", now)
        sign_in_lib(app, session, row.envelope_id)
        both["native"].fetch_signed_pdf(row.envelope_id)
        row.status = "completed"
        with pytest.raises(EsignError) as native_refusal:
            void_envelope(session, both, row, "too late")
        assert native_refusal.value.code == CANNOT_VOID == "ENVELOPE_CANNOT_VOID_INVALID_STATE"
        assert not isinstance(native_refusal.value, be.EsignError) and row.status == "completed"
        done = session.get(EsignEnvelope, "env-2")  # the old vendor's refusal carries the same code
        with pytest.raises(EsignError) as vendor_refusal:
            void_envelope(session, both, done, "too late")
        assert vendor_refusal.value.code == CANNOT_VOID


def test_fetching_before_everyone_signed_is_a_retryable_host_error(tmp_path):
    app = esign_app(tmp_path)
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", "est-7", app.state.clock.utcnow_naive())
        for provider, envelope in ((both["native"], row.envelope_id), (both["fakevendor"], "FV-1")):
            with pytest.raises(EsignError) as refused:
                provider.fetch_signed_pdf(envelope)
            assert refused.value.retryable is True and not isinstance(refused.value, be.EsignError)


def test_the_envelope_json_has_one_shape_for_both_providers(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        items = [legacy_envelope(send(session, both, name, f"est-{n}", now))
                 for n, name in ((7, "fakevendor"), (6, "native"))]
        assert set(items[0]) == set(items[1]) == {"id", "estimate_id", "provider", "envelope_id", "status",
                                                  "signer_name", "signer_email", "client_user_id", "sent_at",
                                                  "completed_at"}
        assert items[0]["sent_at"] == items[1]["sent_at"] == "2026-11-08T10:00:00.000000"
        assert [i["status"] for i in items] == ["sent", "sent"] and [i["provider"] for i in items] == ["fakevendor", "native"]


def test_the_hosts_envelope_route_returns_one_shape_for_both_providers(tmp_path):
    from fastapi.testclient import TestClient

    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        send(session, both, "native", "est-7", now)
        send(session, both, "fakevendor", "est-7", now)
    items = TestClient(app).get("/estimates/est-7/envelopes").json()
    assert len(items) == 2 and {i["provider"] for i in items} == {"native", "fakevendor"}
    assert set(items[0]) == set(items[1]) == {"id", "estimate_id", "provider", "envelope_id", "status", "signer_name",
                                              "signer_email", "client_user_id", "sent_at", "completed_at"}
    assert all(i["sent_at"] == "2026-11-08T10:00:00.000000" for i in items)
    old = TestClient(app).get("/estimates/est-2/envelopes").json()
    assert old[0]["status"] == "completed" and old[0]["completed_at"] == "2026-10-20T12:00:00.000000"


def test_an_overdue_native_request_reports_expired(tmp_path):
    from datetime import timedelta

    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send(session, both, "native", "est-7", now)
        session.get(TABLES.request, row.envelope_id).expires_at = now - timedelta(days=1)
        assert both["native"].status(row.envelope_id) == "expired"
