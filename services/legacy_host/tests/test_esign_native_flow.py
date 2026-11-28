"""The native provider end to end on the host's own page: send, open the link, sign, fetch the signed PDF."""

import inspect
import io
from urllib.parse import parse_qs, urlparse

from esign_util import PDF, esign_app, estimate, providers
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import text

from legacy_host.esign_models import EsignEnvelope
from legacy_host.esign_seam import (
    EsignProvider,
    envelope_status,
    send_for_signature,
    signed_pdf,
    signing_link,
)

PROTOCOL = '''class EsignProvider(Protocol):
    name: str
    def create_envelope(self, *, estimate, pdf: bytes, file_name: str, signer_name: str, signer_email: str,
                        client_user_id: str, email_subject: str) -> str: ...
    def recipient_view_url(self, *, envelope_id: str, signer_name: str, signer_email: str, client_user_id: str,
                           return_url: str) -> str: ...
    def void(self, envelope_id: str, reason: str) -> None: ...
    def fetch_signed_pdf(self, envelope_id: str) -> bytes: ...
    def status(self, envelope_id: str) -> str: ...
'''


def test_the_provider_protocol_is_the_hosts_text_unchanged():
    assert inspect.getsource(EsignProvider) == PROTOCOL


def test_send_open_sign_fetch(tmp_path):
    app = esign_app(tmp_path)
    client = TestClient(app)
    now = app.state.clock.utcnow_naive()
    with app.state.session_factory() as session:
        both = providers(app, session)
        row = send_for_signature(session, both, "native", estimate(session, "est-7"), pdf=PDF, file_name="Estimate 7",
                                 signer_name="Pat Customer", signer_email="pat@example.com", client_user_id="cu-7",
                                 now=now, envelope_class=EsignEnvelope)
        link = signing_link(session, both, row, "http://testserver/estimates/est-7/sign")
        assert urlparse(link).netloc == "testserver" and parse_qs(urlparse(link).query)["sign"] == ["1"]

        page = client.get(link)
        assert page.status_code == 200 and "Estimate 7" in page.text and "typed_name" in page.text
        assert "/esign/static/bond-esign.css" in page.text
        assert client.get("/esign/static/bond-esign.css").status_code == 200
        assert client.get("/esign/static/nope.js").status_code == 404
        assert client.get(link.replace("t=", "t=x")).status_code == 404
        assert client.get(link.replace("est-7", "est-6")).status_code == 404  # a token is for its own estimate

        assert envelope_status(session, both, row, now=now) == "delivered"  # the page was viewed
        refused = client.post(link, content="consent_version=x&mode=typed&typed_name=Pat+Customer",
                              headers={"content-type": "application/x-www-form-urlencoded"})
        assert refused.status_code == 200 and "agree" in refused.text.lower()  # no consent ticked: page again, not signed

        form = f"consent_version={both['native'].consent.version}&consent_accepted=1&mode=typed&typed_name=Pat+Customer"
        done = client.post(link, content=form, headers={"content-type": "application/x-www-form-urlencoded"},
                           follow_redirects=False)
        assert done.status_code == 303 and "signed" in client.get(link).text.lower()

        first = signed_pdf(session, both, row, now=now)
        reader = PdfReader(io.BytesIO(first))
        assert "Accepted by (customer)" in reader.pages[0].extract_text()
        assert "Signature certificate" in reader.pages[-1].extract_text()
        assert row.status == "completed" and row.completed_at == now
        assert signed_pdf(session, both, row, now=now) == first  # the stored copy, byte for byte
    with app.state.session_factory() as session:
        assert session.execute(text("SELECT status, completed_at FROM esign_envelopes WHERE id = :i"),
                               {"i": row.id}).one()[0] == "completed"
