import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from bond_oauth import FakeOAuth, TokenCipher, complete, decode_state, forget_access, start_flow, status
from bond_oauth.handoff_store import HandoffsMixin
from bond_oauth.models import ConnectionsMixin

Base = declarative_base()


class Connection(ConnectionsMixin, Base):
    user_fk_target = None


class Handoff(HandoffsMixin, Base):
    pass


SCOPES = ["gmail.send", "openid", "email"]


def connect(session, cipher, fake, providers, *, user="u1", name="fake", shared=False, scopes=SCOPES, **kw):
    """start, then complete with the fake's code: returns the new connection row."""
    flow = start_flow(session, user_id=user, provider_name=name, provider=fake, scopes=scopes,
                      redirect_to="http://app/x", cipher=cipher, redirect_uri="http://cb", shared=shared)
    kw.setdefault("expected_user_id", user)
    return complete(session, state=flow.state, code="mock", providers=providers, cipher=cipher,
                    connection_model=Connection, redirect_uri="http://cb", expected_nonce=flow.nonce, **kw)


def nonce_of(cipher, state):
    """The nonce inside a hand-made state (a test that gets past the binding check on purpose)."""
    return decode_state(cipher, state).nonce


def stat(session, user="u1"):
    return status(session, user_id=user, provider="fake", connection_model=Connection)


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_access()
    yield
    forget_access()


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def cipher():
    return TokenCipher("unit-test-key")


@pytest.fixture
def fake():
    return FakeOAuth("/consent")


@pytest.fixture
def providers(fake):
    return {"fake": fake}
