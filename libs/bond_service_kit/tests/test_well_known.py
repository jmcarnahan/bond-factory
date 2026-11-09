"""The two well-known files: JSON shapes, headers, 404 when empty, no redirect."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond_service_kit import well_known_router

AASA = "/.well-known/apple-app-site-association"
LINKS = "/.well-known/assetlinks.json"


def client(**kw) -> TestClient:
    app = FastAPI()
    app.include_router(well_known_router(**kw))
    return TestClient(app, follow_redirects=False)


def test_apple_app_site_association_shape():
    resp = client(apple_app_ids=["TEAM123456.org.example.app"], android_apps=[]).get(AASA)
    assert resp.status_code == 200
    assert resp.json() == {
        "applinks": {"details": [{"appIDs": ["TEAM123456.org.example.app"],
                                  "components": [{"/": "/app/return/*"}]}]},
        "webcredentials": {"apps": ["TEAM123456.org.example.app"]},
    }


def test_assetlinks_shape():
    resp = client(apple_app_ids=[], android_apps=[("org.example.app", ["AA:BB", "CC:DD"]),
                                                  ("org.example.two", ["EE:FF"])]).get(LINKS)
    assert resp.status_code == 200
    assert resp.json() == [
        {"relation": ["delegate_permission/common.handle_all_urls"],
         "target": {"namespace": "android_app", "package_name": "org.example.app",
                    "sha256_cert_fingerprints": ["AA:BB", "CC:DD"]}},
        {"relation": ["delegate_permission/common.handle_all_urls"],
         "target": {"namespace": "android_app", "package_name": "org.example.two",
                    "sha256_cert_fingerprints": ["EE:FF"]}},
    ]


def test_headers_json_and_short_cache_and_no_redirect():
    c = client(apple_app_ids=["T.a"], android_apps=[("p", ["F"])])
    for path in (AASA, LINKS):
        resp = c.get(path)
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/json")
        assert resp.headers["cache-control"] == "public, max-age=300"


def test_404_when_the_respective_list_is_empty():
    c = client(apple_app_ids=[], android_apps=[])
    assert c.get(AASA).status_code == 404 and c.get(LINKS).status_code == 404
    only_apple = client(apple_app_ids=["T.a"], android_apps=[])
    assert only_apple.get(AASA).status_code == 200 and only_apple.get(LINKS).status_code == 404
    only_android = client(apple_app_ids=[], android_apps=[("p", ["F"])])
    assert only_android.get(AASA).status_code == 404 and only_android.get(LINKS).status_code == 200


def test_return_path_prefix_is_configurable():
    body = client(apple_app_ids=["T.a"], android_apps=[], return_path_prefix="/back/").get(AASA).json()
    assert body["applinks"]["details"][0]["components"] == [{"/": "/back/*"}]


def test_android_entry_without_fingerprints_is_skipped():
    c = client(apple_app_ids=[], android_apps=[("org.example.none", []), ("org.example.blank", [""])])
    assert c.get(LINKS).status_code == 404
    body = client(apple_app_ids=[], android_apps=[("org.example.none", []), ("org.example.ok", ["AA"])]).get(LINKS).json()
    assert [e["target"]["package_name"] for e in body] == ["org.example.ok"]


def test_blank_entries_are_ignored():
    assert client(apple_app_ids=[""], android_apps=[("", ["F"])]).get(AASA).status_code == 404
