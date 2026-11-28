"""Two providers behind one seam: a row is routed by its `provider` column and by nothing else."""

import pytest
from esign_util import PDF, esign_app, estimate, providers
from sqlalchemy.exc import IntegrityError

from legacy_host.esign_models import EsignEnvelope
from legacy_host.esign_native import NativeProvider
from legacy_host.esign_seam import EsignError, envelope_status, provider_for, send_for_signature


class Spy(NativeProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls: list[str] = []

    def status(self, envelope_id):
        self.calls.append(envelope_id)
        return super().status(envelope_id)


def send(session, both, provider, estimate_id, now):
    return send_for_signature(session, both, provider, estimate(session, estimate_id), pdf=PDF, file_name="Estimate",
                              signer_name="Pat Customer", signer_email="pat@example.com", client_user_id="cu-1",
                              now=now, envelope_class=EsignEnvelope)


def test_each_envelope_stays_with_the_provider_that_made_it(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        spy = Spy(session, both["native"].t, both["native"].consent, both["native"].now, both["native"].store)
        both["native"] = spy
        old = session.get(EsignEnvelope, "env-1")
        vendor_new = send(session, both, "fakevendor", "est-7", now)
        native_new = send(session, both, "native", "est-6", now)
        assert vendor_new.envelope_id.startswith("FV-") and old.provider == vendor_new.provider == "fakevendor"
        assert provider_for(old, both) is both["fakevendor"] and provider_for(vendor_new, both) is both["fakevendor"]
        assert provider_for(native_new, both) is spy
        assert envelope_status(session, both, old, now=now) == "sent"
        assert envelope_status(session, both, vendor_new, now=now) == "sent"
        assert spy.calls == []  # the vendor's rows never reached the native adapter
        assert envelope_status(session, both, native_new, now=now) == "sent"
        assert spy.calls == [native_new.envelope_id]
        # the native adapter does not know a vendor id, and the vendor does not know a native one
        with pytest.raises(EsignError) as native_refusal:
            spy.status("FV-1")
        assert native_refusal.value.code == "ENVELOPE_NOT_FOUND"
        with pytest.raises(EsignError):
            both["fakevendor"].status(native_new.envelope_id)
        ghost = EsignEnvelope(id="env-x", estimate_id="est-1", provider="elsewhere", envelope_id="X-1", status="sent")
        with pytest.raises(EsignError) as unknown:
            provider_for(ghost, both)
        assert unknown.value.code == "UNKNOWN_PROVIDER"


def test_provider_and_envelope_id_are_unique_together(tmp_path):
    app = esign_app(tmp_path)
    with app.state.session_factory() as session:
        session.add(EsignEnvelope(id="dup", estimate_id="est-1", provider="fakevendor", envelope_id="FV-1", status="sent"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(EsignEnvelope(id="other", estimate_id="est-1", provider="native", envelope_id="FV-1", status="sent"))
        session.commit()  # the same id under another provider is a different envelope


def test_both_providers_work_in_one_database_in_one_test(tmp_path):
    app = esign_app(tmp_path)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        a, b = send(session, both, "fakevendor", "est-7", now), send(session, both, "native", "est-6", now)
        for row in (a, b):
            assert envelope_status(session, both, row, now=now) == "sent"
        assert {r.provider for r in session.query(EsignEnvelope).all()} == {"fakevendor", "native"}
