"""The decline form of the public signing page."""

from esign_util import demo, evidence, has_form, kinds, post, request_row, token_of, typed_form

DECLINED = "You declined to sign this document. Nothing was signed."


def decline(client, created, reason="Wrong amount", **extra):
    return client.post(f"/esign/decline/{token_of(created)}", data={"bond_esign_decline_reason": reason, **extra},
                       follow_redirects=False)


def test_the_page_offers_the_decline_form(client):
    created = demo(client)
    page = client.get(created["sign_url"]).text
    assert f'action="/esign/decline/{token_of(created)}"' in page and "Decline to sign" in page
    assert page.count("<form") == 2 and "<script>" not in page


def test_decline_happy_path(client, app):
    created = demo(client)
    reply = decline(client, created)
    assert reply.status_code == 303 and reply.headers["location"] == created["sign_url"]
    assert request_row(app, created).status == "declined"
    declined = [e for e in evidence(client, created)["events"] if e["kind"] == "declined"]
    assert len(declined) == 1 and declined[0]["data"]["reason"] == "Wrong amount"
    page = client.get(reply.headers["location"])
    assert DECLINED in page.text and not has_form(page.text)
    assert DECLINED in client.get(created["sign_url"]).text  # a reload shows the same


def test_decline_without_a_reason(client):
    created = demo(client)
    assert decline(client, created, reason="  ").status_code == 303
    event = next(e for e in evidence(client, created)["events"] if e["kind"] == "declined")
    assert event["data"]["reason"] is None


def test_decline_twice_changes_nothing(client):
    created = demo(client)
    decline(client, created)
    before = kinds(client, created)
    reply = decline(client, created, reason="again")
    assert reply.status_code == 303 and reply.headers["location"].endswith("?error=not_open")
    assert kinds(client, created).count("declined") == before.count("declined") == 1
    assert DECLINED in client.get(created["sign_url"]).text


def test_decline_after_signed_is_refused_and_still_signed(client, app):
    created = demo(client)
    assert post(client, created, typed_form()).status_code == 303
    reply = decline(client, created)
    assert reply.status_code == 303 and "?error=" in reply.headers["location"]
    assert request_row(app, created).status in ("signed", "completed")
    assert "declined" not in kinds(client, created)
    assert "Your signed copy is being prepared." in client.get(created["sign_url"]).text


def test_sign_after_decline_is_refused(client):
    created = demo(client)
    decline(client, created)
    reply = post(client, created, typed_form())
    assert reply.headers["location"].endswith("?error=not_open")
    assert "signed" not in kinds(client, created)


def test_decline_with_an_unknown_token_is_404(client):
    reply = client.post("/esign/decline/nope", data={"bond_esign_decline_reason": "x"}, follow_redirects=False)
    assert reply.status_code == 404


def test_decline_needs_a_urlencoded_form(client):
    created = demo(client)
    reply = client.post(f"/esign/decline/{token_of(created)}", json={"x": 1})
    assert reply.status_code == 415
