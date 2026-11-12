"""Redirect signs before it claims; the disabled 404 is no-store; a custom client_ip is cut once."""

import pytest
from conftest import Grant
from test_grant_seams import PDF, SigningStorage, build, token

from bond_storage import LocalStorageService, grants
from bond_storage.router import MAX_IP_TEXT, NO_STORE


@pytest.fixture
def storage(tmp_path):
    s = LocalStorageService(tmp_path / "store")
    s.upload_bytes(PDF, "c/1/private/a.pdf")
    return s


class FlakySigner(SigningStorage):
    def __init__(self, base):
        super().__init__(base)
        self.fail = True

    def get_url(self, key, expires_in=3600, *, download_filename=None, content_type=None):
        if self.fail:
            raise RuntimeError("signing service down")
        return super().get_url(key, expires_in, download_filename=download_filename, content_type=content_type)


def test_signing_failure_answers_503_and_does_not_burn_the_download(tmp_path, factory, session, doc):
    store = FlakySigner(tmp_path / "s")
    store.upload_bytes(PDF, "c/1/private/a.pdf")
    grant, raw = token(session, doc, max_downloads=1)
    client = build(store, factory, delivery="redirect")
    r = client.get(f"/d/{raw}", follow_redirects=False)
    assert r.status_code == 503
    session.expire_all()
    assert session.get(Grant, grant.id).download_count == 0
    store.fail = False
    r = client.get(f"/d/{raw}", follow_redirects=False)  # the retry works
    assert r.status_code == 302
    session.expire_all()
    assert session.get(Grant, grant.id).download_count == 1
    assert client.get(f"/d/{raw}", follow_redirects=False).status_code == 410  # now used up


def test_disabled_404_carries_the_no_store_headers(storage, factory, session, doc):
    _, raw = token(session, doc)
    r = build(storage, factory, enabled=lambda: False).get(f"/d/{raw}")
    assert r.status_code == 404
    for name, value in NO_STORE.items():
        assert r.headers[name.lower()] == value


def test_a_long_custom_client_ip_is_cut_before_the_limiter_and_on_claim(storage, factory, session, doc):
    _, raw = token(session, doc)
    seen = {}
    client = build(storage, factory, client_ip=lambda request: "9" * 300,
                   rate_limit=lambda key, ip: seen.setdefault("limiter", ip) is not None,
                   on_claim=lambda s, g, ip: seen.setdefault("claim", ip))
    assert client.get(f"/d/{raw}").status_code == 200
    assert seen["limiter"] == "9" * MAX_IP_TEXT == seen["claim"]


def test_lib_columns_equal_the_mixins_real_table_columns():
    assert grants.LIB_COLUMNS == {c.name for c in Grant.__table__.columns}
