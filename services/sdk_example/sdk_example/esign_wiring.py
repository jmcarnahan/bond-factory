"""E-signing wiring (bond_esign): the tables, the consent, where the two PDFs live, the client IP, the completion job.

COPY, then replace (README has the table): the consent company and contact, the storage keys, the staff guard
(`routes/esign.py`), the zone, and the IP rule. The library stores no PDF and sends no mail: this file stores both
PDFs through `app.state.storage` and the job below stops where the app would send the signed copy.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import bond_jobs
from bond_esign import (
    RequestContext,
    Tables,
    build_signed_pdf,
    complete,
    default_consent,
    expire_due,
)
from fastapi import FastAPI, Request

from . import wiring
from .models.esign import EsignEvent, EsignRequest, EsignSigner
from .models.jobs import BackgroundJob

log = logging.getLogger("sdk_example")
TABLES = Tables(request=EsignRequest, signer=EsignSigner, event=EsignEvent)
CONSENT = default_consent(company_name="Sample Company", paper_contact="office@example.com")
JOB_TYPE = "esign_complete"
PDF = "application/pdf"


def original_key(request_id: str) -> str:
    return f"esign/{request_id}/original.pdf"


def signed_key(request_id: str) -> str:
    return f"esign/{request_id}/signed.pdf"


def store_original(app: FastAPI, request_id: str, pdf: bytes) -> None:
    app.state.storage.upload_bytes(pdf, original_key(request_id), content_type=PDF)


def load_original(app: FastAPI, request_id: str) -> bytes:
    return app.state.storage.download_bytes(original_key(request_id))


def load_signed(app: FastAPI, request_id: str) -> bytes:
    return app.state.storage.download_bytes(signed_key(request_id))


def request_context(request: Request) -> RequestContext:
    """Who is signing, as the evidence records it.

    The IP is `wiring.client_ip`: the last hop of X-Forwarded-For, else the socket peer. That is right only behind ONE
    proxy that appends the header. A real app uses its framework's trusted-proxy setting (or reads the one header its
    load balancer sets): a client-supplied X-Forwarded-For must never become evidence."""
    return RequestContext(ip=wiring.client_ip(request), user_agent=request.headers.get("user-agent"))


def enqueue_completion(session: Any, request_id: str, now: datetime) -> None:
    """Queue the build once per request (the key makes a second call a no-op)."""
    bond_jobs.enqueue(session, BackgroundJob, JOB_TYPE, {"request_id": request_id}, key=f"{JOB_TYPE}:{request_id}",
                      now=now)


def expire_overdue(session: Any, now: datetime) -> int:
    """Close every open request past its `expires_at` (status `expired`, one `expired` event each).

    Runs from the job tick's `before` hook (routes/jobs.py in fake mode; an app's worker loop passes it as the `then`
    of `sweep_wiring.before_hook`, or calls `expire_due` from its own scheduler). The tick commits the session."""
    return expire_due(session, TABLES, now=now)


def install(app: FastAPI) -> None:
    @app.state.job_registry.handler(JOB_TYPE)
    def esign_complete(session: Any, payload: dict, now: datetime) -> dict:
        """Build the signed PDF, store it, record it. Only a `signed` request is built: a `completed` one is skipped,
        so a stored copy is never overwritten (a rebuild under a changed zone or a seal would differ from the hash
        on the row). A request that cannot complete (voided, declined, expired, gone) is skipped too. Any
        `EsignError` (`evidence_mismatch`, `document_mismatch`, ...) or storage failure is NOT swallowed: the job
        retries and goes dead where it is visible. Store before `complete`: a failed store leaves `signed`."""
        request = session.get(TABLES.request, payload["request_id"])
        if request is None or request.status != "signed":
            return {"skipped": True, "reason": "nothing to build"}
        signed = build_signed_pdf(session, TABLES, request, pdf=load_original(app, request.id),
                                  zone=app.state.settings.tz)
        app.state.storage.upload_bytes(signed.pdf, signed_key(request.id), content_type=PDF)  # before `complete`
        complete(session, TABLES, request, signed=signed, now=now)
        # NOT sent here: the demo mails nothing. A real app emails the signed copy now and then calls
        # `record_delivery(session, TABLES, request, channel="email", reference=<message id>, now=now)`.
        return {"summary": f"signed copy of {request.id[:8]} built ({signed.pages} pages)"}
