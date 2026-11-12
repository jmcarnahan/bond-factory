"""Grant seams: ``extra`` columns, ``on_claim``, redirect delivery, ``gone_body``, ``enabled``, ``enforce_cap``."""

import pytest
import sqlalchemy as sa
from conftest import Base, Grant, load_document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Mapped, mapped_column

from bond_storage import (
    GrantsMixin,
    GrantUnavailable,
    LocalStorageService,
    claim,
    make_download_router,
    mint,
    resolve,
)
from bond_storage.router import GONE_BODY

PDF = b"%PDF-1.4 test"


class CampaignGrant(GrantsMixin, Base):
    """A grant table with the lib's mixin plus one app column."""

    __tablename__ = "campaign_grants"
    campaign: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)


class SigningStorage(LocalStorageService):
    """Local files, but it presigns like S3 and records what it was asked."""

    def __init__(self, base, on_exists=None):
        super().__init__(base)
        self.on_exists, self.signed = on_exists, []

    @property
    def supports_presigned(self):
        return True

    def exists(self, key):
        if self.on_exists:
            self.on_exists()
        return super().exists(key)

    def get_url(self, key, expires_in=3600, *, download_filename=None, content_type=None):
        self.signed.append((key, expires_in, download_filename, content_type))
        return f"https://signed.example.com/{key}?expires={expires_in}"

    def download_bytes(self, key):
        raise AssertionError("redirect mode must not read the bytes")


@pytest.fixture
def storage(tmp_path):
    s = LocalStorageService(tmp_path / "store")
    s.upload_bytes(PDF, "c/1/private/a.pdf")
    return s


def build(storage, factory, **kw):
    app = FastAPI()
    app.include_router(make_download_router(storage=storage, grant_model=Grant, document_loader=load_document,
                                            session_factory=factory, **kw))
    return TestClient(app, raise_server_exceptions=False)


def token(session, doc, **kw):
    grant, raw = mint(session, doc, grant_model=Grant, user_id="u", **kw)
    session.commit()
    return grant, raw


def test_mint_extra_columns(session, doc):
    grant, raw = mint(session, doc, grant_model=CampaignGrant, user_id="u", extra={"campaign": "spring"})
    session.commit()
    assert grant.campaign == "spring" and grant.created_by == "u" and grant.document_id == "d1"
    found, _ = resolve(session, raw, grant_model=CampaignGrant, document_loader=load_document)
    assert found.campaign == "spring"
    plain, _ = mint(session, doc, grant_model=CampaignGrant, user_id="u")
    assert plain.campaign is None


def test_mint_extra_cannot_override_lib_columns(session, doc):
    for key in ("purpose", "token_hash", "download_count", "expires_at", "id"):
        with pytest.raises(ValueError, match=key):
            mint(session, doc, grant_model=Grant, user_id="u", extra={key: "x"})


def test_resolve_without_cap(session, doc):
    grant, raw = mint(session, doc, grant_model=Grant, user_id="u", max_downloads=1)
    session.commit()
    assert claim(session, grant, "1.1.1.1")
    with pytest.raises(GrantUnavailable):
        resolve(session, raw, grant_model=Grant, document_loader=load_document)
    found, _ = resolve(session, raw, grant_model=Grant, document_loader=load_document, enforce_cap=False)
    assert found.id == grant.id
    assert claim(session, grant, "1.1.1.1", enforce_cap=False) and grant.download_count == 2
    assert not claim(session, grant, "1.1.1.1")


def test_router_on_claim_runs_in_same_commit(storage, factory, session, doc):
    grant, raw = token(session, doc)
    calls = []

    def hook(s, g, ip):
        calls.append((g.id, ip, g.download_count))
        # still uncommitted here: a second connection would not see the count yet, this session does
        s.add(Grant(token_hash="marker", document_id="d1", purpose="marker", expires_at=g.expires_at))

    r = build(storage, factory, on_claim=hook).get(f"/d/{raw}")
    assert r.status_code == 200 and calls == [(grant.id, "testclient", 1)]
    session.expire_all()
    assert session.query(Grant).filter_by(purpose="marker").count() == 1
    assert session.get(Grant, grant.id).download_count == 1


def test_router_on_claim_raise_rolls_back_claim(storage, factory, session, doc):
    grant, raw = token(session, doc)

    def hook(s, g, ip):
        s.add(Grant(token_hash="marker", document_id="d1", purpose="marker", expires_at=g.expires_at))
        raise RuntimeError("audit write failed")

    r = build(storage, factory, on_claim=hook).get(f"/d/{raw}")
    assert r.status_code == 500
    session.expire_all()
    assert session.get(Grant, grant.id).download_count == 0
    assert session.query(Grant).filter_by(purpose="marker").count() == 0


def test_router_redirect_checks_exists_before_claim(tmp_path, factory, session, doc):
    counts = []
    store = SigningStorage(tmp_path / "s", on_exists=lambda: counts.append(session.get(Grant, grant.id).download_count))
    store.upload_bytes(PDF, "c/1/private/a.pdf")
    grant, raw = token(session, doc)
    session.expire_all()
    r = build(store, factory, delivery="redirect", presign_seconds=45).get(f"/d/{raw}", follow_redirects=False)
    assert r.status_code == 302 and counts == [0]
    assert r.headers["location"] == "https://signed.example.com/c/1/private/a.pdf?expires=45"
    assert r.headers["cache-control"].startswith("no-store")
    assert store.signed == [("c/1/private/a.pdf", 45, None, "application/pdf")]  # pdf opens inline: no forced name
    session.expire_all()
    assert session.get(Grant, grant.id).download_count == 1


def test_router_redirect_missing_object_is_410_and_not_counted(tmp_path, factory, session, doc):
    store = SigningStorage(tmp_path / "s")  # nothing uploaded
    grant, raw = token(session, doc)
    r = build(store, factory, delivery="redirect").get(f"/d/{raw}", follow_redirects=False)
    assert r.status_code == 410 and r.text == GONE_BODY
    session.expire_all()
    assert session.get(Grant, grant.id).download_count == 0


def test_router_redirect_forces_the_name_for_downloads(tmp_path, factory, session, doc):
    doc.content_type = "text/html"
    session.commit()
    store = SigningStorage(tmp_path / "s")
    store.upload_bytes(PDF, "c/1/private/a.pdf")
    _, raw = token(session, doc)
    build(store, factory, delivery="redirect").get(f"/d/{raw}", follow_redirects=False)
    assert store.signed[0][2:] == ("a.pdf", "text/html")


def test_router_redirect_falls_back_to_stream_on_local(storage, factory, session, doc):
    grant, raw = token(session, doc)
    r = build(storage, factory, delivery="redirect").get(f"/d/{raw}", follow_redirects=False)
    assert r.status_code == 200 and r.content == PDF
    session.expire_all()
    assert session.get(Grant, grant.id).download_count == 1


def test_redirect_with_after_download_is_refused(storage, factory):
    with pytest.raises(ValueError, match="after_download"):
        make_download_router(storage=storage, grant_model=Grant, document_loader=load_document,
                             session_factory=factory, delivery="redirect", after_download=lambda s, d: None)
    with pytest.raises(ValueError, match="delivery"):
        make_download_router(storage=storage, grant_model=Grant, document_loader=load_document,
                             session_factory=factory, delivery="bogus")  # type: ignore[arg-type]


def test_gone_body_and_enabled_flag(storage, factory, session, doc):
    _, raw = token(session, doc)
    custom = build(storage, factory, gone_body="<p>custom</p>")
    bad = custom.get("/d/nope")
    assert bad.status_code == 410 and bad.text == "<p>custom</p>"
    callable_body = build(storage, factory, gone_body=lambda request: f"<p>{request.url.path}</p>")
    assert callable_body.get("/d/nope").text == "<p>/d/nope</p>"
    assert build(storage, factory).get("/d/nope").text == GONE_BODY  # default unchanged

    on = {"value": False}
    gated = build(storage, factory, enabled=lambda: on["value"])
    assert gated.get(f"/d/{raw}").status_code == 404
    assert gated.get("/d/nope").status_code == 404
    on["value"] = True
    assert gated.get(f"/d/{raw}").status_code == 200


def test_client_ip_option(storage, factory, session, doc):
    grant, raw = token(session, doc)
    build(storage, factory, client_ip=lambda request: "9.9.9.9").get(f"/d/{raw}")
    session.expire_all()
    assert session.get(Grant, grant.id).last_ip == "9.9.9.9"


def test_router_enforce_cap_false_serves_past_the_cap(storage, factory, session, doc):
    _, raw = token(session, doc, max_downloads=1)
    app = build(storage, factory, enforce_cap=False)
    assert app.get(f"/d/{raw}").status_code == 200 and app.get(f"/d/{raw}").status_code == 200
    assert build(storage, factory).get(f"/d/{raw}").status_code == 410
