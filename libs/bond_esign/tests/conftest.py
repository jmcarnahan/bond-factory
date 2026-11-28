import io
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_esign import (
    Consent,
    EsignError,
    EsignEventMixin,
    EsignSignerMixin,
    Placement,
    RequestContext,
    SignerSpec,
    Tables,
    TenantEsignRequestMixin,
    create_request,
    sign,
)

NOW = datetime(2026, 11, 8, 10, 0)
CONSENT = Consent(version="consent/1", language="en", text="I agree to sign this document electronically.")
PLACEMENT = Placement(page=-1, x=0.2, y=0.8, w=0.3, h=0.06)


class Base(DeclarativeBase):
    pass


class Request(TenantEsignRequestMixin, Base):
    pass


class Signer(EsignSignerMixin, Base):
    pass


class Event(EsignEventMixin, Base):
    pass


T = Tables(request=Request, signer=Signer, event=Event)


def make_engine(url="sqlite://", **kw):
    engine = create_engine(url, **kw)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture
def engine():
    eng = make_engine(poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


def make_pdf(pages: int = 2, tag: str = "") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, invariant=1)
    for n in range(pages):
        c.drawString(72, 700, f"Synthetic estimate, page {n + 1}")
        if tag:
            c.drawString(72, 650, tag)
        c.showPage()
    c.save()
    return buf.getvalue()


def signed_doc(tag: str = "a", pages: int = 3, **kw):
    """A SignedDocument whose hash and page count are true (complete() checks them)."""
    from bond_esign import SignedDocument, sha256_hex

    pdf = make_pdf(pages, tag)
    return SignedDocument(pdf=pdf, sha256=sha256_hex(pdf), pages=pages, **kw)


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf(2)


def sig_png(width: int = 300, height: int = 120, transparent: bool = True, pad: int = 40) -> bytes:
    """A drawn-looking signature: a thick zigzag line inside blank margins."""
    bg = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
    img = Image.new("RGBA", (width, height), bg)
    draw = ImageDraw.Draw(img)
    pts = [(pad, height - pad), (pad + 40, pad), (pad + 80, height - pad), (width - pad, pad)]
    draw.line(pts, fill=(10, 10, 60, 255), width=4)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def blank_png(width: int = 200, height: int = 80) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(out, format="PNG")
    return out.getvalue()


def new_request(session, pdf, *, signers=None, now=NOW, **kw):
    signers = signers if signers is not None else [SignerSpec(name="Pat Example", placement=PLACEMENT)]
    kw.setdefault("title", "Estimate 100")
    kw.setdefault("consent", CONSENT)
    return create_request(session, T, pdf=pdf, signers=signers, now=now, **kw)


def signers_of(session, request):
    from sqlalchemy import select

    return list(
        session.execute(select(Signer).where(Signer.request_id == request.id).order_by(Signer.position)).scalars()
    )


def at(minutes: int = 0, seconds: int = 0) -> datetime:
    return NOW + timedelta(minutes=minutes, seconds=seconds)


CTX = RequestContext(ip="203.0.113.7", user_agent="TestAgent/1.0")


@contextmanager
def expect(code):
    """The block must raise EsignError with this code."""
    with pytest.raises(EsignError) as info:
        yield
    assert info.value.code == code, f"got {info.value.code!r}: {info.value.message}"
    assert info.value.message


def sign_it(session, signer, pdf, **over):
    args = {
        "pdf": pdf, "consent_version": CONSENT.version, "consent_accepted": True, "typed_name": "Pat Example",
        "drawn_png": None, "ctx": CTX, "now": at(1),
    }  # fmt: skip
    args.update(over)
    return sign(session, T, signer, **args)


def events_of(session, request):
    from bond_esign import chain

    return chain(session, T, request)


def kinds_of(session, request):
    return [e.kind for e in events_of(session, request)]
