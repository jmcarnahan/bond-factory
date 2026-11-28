"""Helpers for the e-signing route tests."""

import base64
import io
import re
from datetime import datetime

from connections_util import headers
from PIL import Image, ImageDraw
from pypdf import PdfReader

from sdk_example.db import session_scope
from sdk_example.esign_wiring import CONSENT, TABLES


def demo(client, **body):
    reply = client.post("/esign/demo", json=body)
    assert reply.status_code == 200, reply.text
    return reply.json()


def token_of(created: dict) -> str:
    return created["sign_url"].rsplit("/", 1)[-1]


def typed_form(name="Pat Sample", **over) -> dict:
    form = {"consent_version": CONSENT.version, "consent_accepted": "1", "mode": "typed", "typed_name": name,
            "drawn_png": ""}
    return {**form, **over}


def drawn_form(**over) -> dict:
    image = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    ImageDraw.Draw(image).line([(40, 80), (80, 40), (120, 80), (260, 40)], fill=(10, 10, 60, 255), width=4)
    out = io.BytesIO()
    image.save(out, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()
    return typed_form(name="Pat Sample", mode="drawn", drawn_png=url, **over)


def post(client, created: dict, form: dict):
    return client.post(created["sign_url"], data=form, follow_redirects=False)


def tick(client, now="2026-11-08T10:05:00Z"):
    return client.post("/jobs/tick", json={"now": now}, headers=headers(client)).json()


def evidence(client, created: dict) -> dict:
    reply = client.get(f"/esign/requests/{created['request_id']}/evidence", headers=headers(client))
    assert reply.status_code == 200, reply.text
    return reply.json()


def kinds(client, created: dict) -> list[str]:
    return [e["kind"] for e in evidence(client, created)["events"]]


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def pages(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def request_row(app, created: dict):
    with session_scope(app.state.session_factory) as session:
        row = session.get(TABLES.request, created["request_id"])
        session.expunge(row)
        return row


def has_form(html: str) -> bool:
    return re.search(r"<form", html) is not None


NOW = datetime(2026, 11, 8, 10, 0)
