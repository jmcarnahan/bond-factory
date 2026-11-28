"""Private helpers shared by the service modules: time, statuses, row locks, the stored policy."""

import dataclasses
from datetime import UTC, datetime

from sqlalchemy import select

from bond_esign.types import Policy, RequestContext, Tables

OPEN, SIGNED, COMPLETED, DECLINED, VOIDED, EXPIRED = (
    "open", "signed", "completed", "declined", "voided", "expired",
)
PENDING = "pending"  # a signer that has not yet signed or declined
METHODS = ("link", "app_link", "email_code", "in_person")
ISO = "%Y-%m-%dT%H:%M:%SZ"


def utc(moment: datetime) -> datetime:
    """Naive UTC, whole seconds: the one shape every stored time and every hash input has."""
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment.replace(microsecond=0)


def iso(moment: datetime | None) -> str | None:
    return None if moment is None else utc(moment).strftime(ISO)


_CONTROLS = {c: None for c in [*range(9), *range(11, 32), 127]}  # C0 and DEL, keeping \t (9) and \n (10)


def clean(text: str | None, limit: int) -> str | None:
    """Text safe to store and hash: unencodable characters replaced, NUL and other control characters
    (not \\n, \\t) removed, cut to ``limit``."""
    if text is None:
        return None
    text = str(text).encode("utf-8", "replace").decode("utf-8")  # a lone surrogate would fail on its way to the database
    return text.translate(_CONTROLS)[:limit]


def clean_ctx(ctx: RequestContext | None) -> RequestContext:
    """The request context as it is stored: ip 64, user agent 1000, actor 200 characters, controls stripped."""
    ctx = ctx or RequestContext()
    return RequestContext(ip=clean(ctx.ip, 64), user_agent=clean(ctx.user_agent, 1000), actor=clean(ctx.actor, 200))


def request_of(session, t: Tables, signer):
    return session.get(t.request, signer.request_id)


def lock(session, t: Tables, request, signer=None) -> None:
    """Take the row lock on the request (a no-op on SQLite) and reload it, and the signer, from the database.

    Pending changes are flushed first: the reload would otherwise throw away unflushed edits (autoflush off).
    """
    session.flush()
    session.execute(
        select(t.request)
        .where(t.request.id == request.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    if signer is not None:
        session.execute(
            select(t.signer).where(t.signer.id == signer.id).execution_options(populate_existing=True)
        ).scalar_one()


def policy_of(request) -> Policy:
    """Rebuild the ``Policy`` frozen at creation: unknown keys are ignored, missing keys take the default."""
    known = {f.name for f in dataclasses.fields(Policy)}
    return Policy(**{k: v for k, v in (request.policy or {}).items() if k in known})
