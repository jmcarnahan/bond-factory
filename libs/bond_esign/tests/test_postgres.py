"""Row locks and the unique (request_id, seq) constraint. Postgres-marked tests need BOND_TEST_POSTGRES_URL."""

import os
import threading
from datetime import timedelta

import pytest
from conftest import CONSENT, NOW, PLACEMENT, Base, T, at, make_engine, make_pdf, sign_it
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bond_esign import EsignError, SignerSpec, append, chain, create_request, events, expire_due, verify_chain

THREADS = 8


@pytest.fixture
def pg_url():
    url = os.environ.get("BOND_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BOND_TEST_POSTGRES_URL is not set")
    return url


@pytest.fixture
def pg_engine(pg_url):
    engine = make_engine(pg_url, pool_size=THREADS + 2)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def run_together(engine, jobs):
    """Run each ``job(session)`` in its own thread and session, released together. Returns the results."""
    factory = sessionmaker(engine, expire_on_commit=False)
    barrier = threading.Barrier(len(jobs))
    results, errors = [None] * len(jobs), []

    def worker(index, job):
        try:
            with factory() as s:
                barrier.wait(timeout=30)
                results[index] = job(s)
                s.commit()
        except BaseException as exc:  # noqa: BLE001  collected and re-raised in the test thread
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i, j)) for i, j in enumerate(jobs)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(120)
    assert not errors, errors
    return results


def seed(engine, signers=1):
    pdf = make_pdf(2)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        request = create_request(
            s, T, pdf=pdf, title="T", consent=CONSENT, now=NOW,
            signers=[SignerSpec(f"Signer {n}", placement=PLACEMENT) for n in range(signers)],
        )  # fmt: skip
        ids = (request.id, [x.id for x in s.execute(select(T.signer).order_by(T.signer.position)).scalars()])
        s.commit()
    return pdf, ids


@pytest.mark.postgres
def test_concurrent_appends_never_collide_on_seq_and_the_chain_verifies(pg_engine):
    _, (request_id, _) = seed(pg_engine)

    def job(n):
        def run(s):
            request = s.get(T.request, request_id)
            for k in range(5):
                append(s, T, request, events.VIEWED, data={"n": n, "k": k}, now=at(n, k))

        return run

    run_together(pg_engine, [job(n) for n in range(THREADS)])
    with sessionmaker(pg_engine)() as s:
        request = s.get(T.request, request_id)
        rows = chain(s, T, request)
        assert [r.seq for r in rows] == list(range(1, 1 + 1 + THREADS * 5))
        check = verify_chain(s, T, request)
        assert (check.ok, check.count) == (True, 1 + THREADS * 5)


@pytest.mark.postgres
def test_two_signers_signing_at_once_both_land_and_the_request_becomes_signed(pg_engine):
    pdf, (request_id, signer_ids) = seed(pg_engine, signers=2)

    def job(signer_id):
        def run(s):
            signer = s.get(T.signer, signer_id)
            return sign_it(s, signer, pdf, now=at(1)).all_signed

        return run

    done = run_together(pg_engine, [job(i) for i in signer_ids])
    assert sorted(done) == [False, True]  # exactly one of them finished the request
    with sessionmaker(pg_engine)() as s:
        request = s.get(T.request, request_id)
        kinds = [e.kind for e in chain(s, T, request)]
        assert request.status == "signed"
        assert kinds.count("signed") == 2 and kinds.count("consent_given") == 2
        assert verify_chain(s, T, request).ok


@pytest.mark.postgres
def test_the_same_signer_submitting_twice_at_once_signs_once_and_the_other_is_a_replay(pg_engine):
    pdf, (request_id, signer_ids) = seed(pg_engine)

    def run(s):
        return sign_it(s, s.get(T.signer, signer_ids[0]), pdf, now=at(1)).replay

    replays = run_together(pg_engine, [run, run, run])
    assert sorted(replays) == [False, True, True]
    with sessionmaker(pg_engine)() as s:
        request = s.get(T.request, request_id)
        kinds = [e.kind for e in chain(s, T, request)]
        assert kinds.count("signed") == 1 and verify_chain(s, T, request).ok


@pytest.mark.postgres
def test_two_expiry_sweeps_at_once_write_one_expired_event(pg_engine):
    _, (request_id, _) = seed(pg_engine)
    with sessionmaker(pg_engine)() as s:
        s.get(T.request, request_id).expires_at = NOW + timedelta(minutes=5)
        s.commit()
    flipped = run_together(pg_engine, [lambda s: expire_due(s, T, now=at(10))] * 3)
    assert sorted(flipped) == [0, 0, 1]
    with sessionmaker(pg_engine)() as s:
        request = s.get(T.request, request_id)
        assert [e.kind for e in chain(s, T, request)].count("expired") == 1 and verify_chain(s, T, request).ok


@pytest.mark.postgres
def test_signing_and_the_expiry_sweep_at_once_never_both_win(pg_engine):
    pdf, (request_id, signer_ids) = seed(pg_engine)
    with sessionmaker(pg_engine)() as s:
        s.get(T.request, request_id).expires_at = NOW + timedelta(minutes=5)
        s.commit()

    def signing(s):
        try:
            sign_it(s, s.get(T.signer, signer_ids[0]), pdf, now=at(1))
        except EsignError as exc:
            return exc.code
        return "signed"

    outcome, _ = run_together(pg_engine, [signing, lambda s: expire_due(s, T, now=at(10))])
    with sessionmaker(pg_engine)() as s:
        request = s.get(T.request, request_id)
        kinds = [e.kind for e in chain(s, T, request)]
        assert (outcome, request.status) in {("signed", "signed"), ("expired", "expired")}
        assert kinds.count("expired") == (1 if request.status == "expired" else 0)
        assert verify_chain(s, T, request).ok


def test_a_forced_duplicate_seq_is_an_integrity_error_not_a_second_row():
    """No Postgres needed: the unique (request_id, seq) constraint is what makes a lost race loud."""
    engine = make_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        request = create_request(s, T, pdf=make_pdf(1), title="T", consent=CONSENT, now=NOW,
                                 signers=[SignerSpec("A")])  # fmt: skip
        s.commit()
        row = {"request_id": request.id, "seq": 1, "kind": "viewed", "at": NOW, "data": {}, "prev_hash": "0" * 64,
               "row_hash": "f" * 64}  # fmt: skip
        with pytest.raises(IntegrityError):
            s.execute(insert(T.event).values(id="dup", **row))
        s.rollback()
        assert len(chain(s, T, request)) == 1
