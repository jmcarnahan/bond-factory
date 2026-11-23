"""The ported label tool cannot spend by accident, reads the key only from the environment, handles no address and makes
no network call of its own. No API call is made by any test here (the anthropic module is replaced by a tripwire)."""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import roof_eval_helpers as H

from tools.roof_eval.label import __main__ as cli
from tools.roof_eval.label import driver, make_truth

PKG = Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "label"


@pytest.fixture(autouse=True)
def no_api(monkeypatch):
    """Importing anthropic anywhere in these tests is a failure."""

    class Tripwire:
        def __getattr__(self, name):
            raise AssertionError(f"anthropic.{name} touched: a test tried to reach the API")

    monkeypatch.setitem(sys.modules, "anthropic", Tripwire())
    monkeypatch.setattr(driver, "run_queue", lambda *a, **k: pytest.fail("the queue started"))
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: pytest.fail("a child process started"))


def refuses(argv, monkeypatch, key=True):
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    return str(e.value)


def test_run_without_the_spend_flags_refuses(monkeypatch, tmp_path):
    w = ["run", "--work-dir", str(tmp_path)]
    msg = refuses(w, monkeypatch)
    assert "--spend-cap" in msg and "--confirm-spend" in msg
    assert "--confirm-spend" in refuses(
        w + ["--spend-cap", "10"], monkeypatch
    ) and "--spend-cap" not in refuses(w + ["--spend-cap", "10"], monkeypatch)
    assert "--spend-cap" in refuses(w + ["--confirm-spend"], monkeypatch)
    assert "--spend-cap" in refuses(w + ["--confirm-spend", "--spend-cap", "0"], monkeypatch)
    assert "--spend-cap" in refuses(w + ["--confirm-spend", "--spend-cap", "-5"], monkeypatch)


def test_run_without_a_key_in_the_environment_refuses(monkeypatch, tmp_path):
    msg = refuses(
        ["run", "--work-dir", str(tmp_path), "--spend-cap", "10", "--confirm-spend"], monkeypatch, key=False
    )
    assert "ANTHROPIC_API_KEY is not set" in msg


def test_one_without_the_flags_refuses_but_render_only_and_dump_request_need_none(monkeypatch, tmp_path):
    house = make_house(tmp_path / "h-00000001")
    base = ["one", str(house), "--out", str(tmp_path / "out")]
    assert "--spend-cap" in refuses(base, monkeypatch)
    assert "--confirm-spend" in refuses(base + ["--spend-cap", "5"], monkeypatch)
    # --render-only spends nothing: it must run with no flags and no key (renders pictures, returns before the API section)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(base + ["--render-only"]) == 0
    assert (tmp_path / "out" / "a_height.png").exists()


def test_one_checks_the_cap_against_the_ledger_and_needs_a_ledger(monkeypatch, tmp_path):
    house = make_house(tmp_path / "h-00000003")
    base = ["one", str(house), "--out", str(tmp_path / "out"), "--spend-cap", "10", "--confirm-spend", "--max-cost", "5.5"]
    assert "--spend LEDGER" in refuses(base, monkeypatch)  # no ledger path: refused
    led = tmp_path / "spend.tsv"
    ledger(tmp_path, 4.6)  # 4.6 + 5.5 = 10.1 > 10
    msg = refuses(base + ["--spend", str(led)], monkeypatch)
    assert "ledger total 4.60" in msg and "passes --spend-cap" in msg
    ledger(tmp_path, 4.5)  # 4.5 + 5.5 = 10.0: inside the cap, so the run is handed on (stubbed: no rendering, no API)
    called = []
    monkeypatch.setattr(make_truth, "run", lambda *a, **k: called.append(k.get("confirm_spend")))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    assert cli.main(base + ["--spend", str(led)]) == 0 and called == [True]


def test_run_itself_refuses_without_confirm_even_when_called_directly(monkeypatch, tmp_path):
    house = make_house(tmp_path / "h-00000002")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    with pytest.raises(SystemExit, match="confirm_spend"):
        make_truth.run(house, tmp_path / "out")  # renders and audits, then refuses before importing anthropic
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        make_truth.run(house, tmp_path / "out", confirm_spend=True)


def test_the_key_is_read_only_from_the_environment():
    src = "\n".join(p.read_text() for p in PKG.glob("*.py"))
    assert src.count("os.environ") >= 3  # the CLI check, make_truth's check, the child environment
    assert (
        "anthropic.Anthropic(timeout=900.0)" in src and "api_key" not in src
    )  # the client finds the key itself
    assert "dotenv" not in src and not re.search(r"open\([^)]*(env|key|secret)", src, re.IGNORECASE)
    assert "print(os.environ" not in src and "print(ENV" not in src and "print(child_env" not in src


def test_no_address_no_network_no_private_paths_in_the_ported_code():
    src = {p.name: p.read_text() for p in PKG.glob("*.py")}
    for name, text in src.items():
        for bad in (
            "slug",
            "urllib",
            "requests",
            "http://",
            "https://",
            "noaa",
            "naip",
            "/Users/",
            "scratchpad",
            "ortho",
        ):
            assert bad not in text.lower(), f"{name}: {bad}"
        assert not re.search(r"\b\d{3,5} +[A-Z][a-z]+ +(St|Ave|Rd|Dr|Ln|Blvd)\b", text), name
        assert not re.search(r"-1[01]\d\.\d{4,}", text), name  # no coordinate


def test_child_environment_is_minimal(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("SOME_SECRET", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "y")
    assert set(driver.child_env()) <= {"PATH", "HOME", "ANTHROPIC_API_KEY"}
    assert "SOME_SECRET" not in driver.child_env()


# ---- the budget gate ----
def ledger(work, *usd):
    rows = [
        "utc\thouse_id\ttag\tinput_tokens\toutput_tokens\tcache_read_tokens\tcache_write_tokens\tusd_estimate\tstop"
    ]
    rows += [f"t\th-0000000{i}\tr1\t0\t0\t0\t0\t{u}\tdone" for i, u in enumerate(usd)]
    (work / "spend.tsv").write_text("\n".join(rows) + "\n")


def test_the_cap_counts_earlier_spend_and_the_reserve_of_every_run_in_flight(tmp_path):
    g = driver.Gate(tmp_path, spend_cap=20.0, reserve=5.5)
    assert g.spent() == 0.0 and g.may_start()
    ledger(tmp_path, 4.0, 6.0)
    assert g.spent() == 10.0 and g.may_start(1) and g.may_start(1)
    assert g.may_start(1) and not g.may_start(2)  # 10 + 11 = 21 > 20
    g.inflight = 1
    assert not g.may_start(1)  # 10 + 5.5 * 2 = 21 > 20
    g.inflight = 0
    ledger(tmp_path, 14.5)
    assert g.may_start(1)  # 14.5 + 5.5 = 20.0: inclusive
    ledger(tmp_path, 14.6)
    assert not g.may_start(1)
    ledger(tmp_path, 20.0)
    assert not g.may_start(1)  # already at the cap


def test_nothing_starts_over_budget_and_the_refusal_is_logged(tmp_path):
    ledger(tmp_path, 19.0)
    g = driver.Gate(tmp_path, spend_cap=20.0)
    driver.one(g, "h-00000009", "/x/h-00000009", "r1")  # subprocess.run is a tripwire in this file
    assert "BUDGET: not starting h-00000009 r1" in (tmp_path / "logs" / "driver.log").read_text()
    assert g.inflight == 0


def test_a_house_is_skipped_when_both_runs_do_not_fit(tmp_path):
    ledger(tmp_path, 9.0)  # one run fits (9 + 5.5 <= 19.9) but two do not (9 + 11 = 20 > 19.9)
    g = driver.Gate(tmp_path, spend_cap=19.9)
    (tmp_path / "houses.tsv").write_text("id\tfolder\nh-00000009\t/x\n")
    driver.house(g, {"id": "h-00000009", "folder": "/x"})
    assert "BUDGET: skipping house h-00000009" in (tmp_path / "logs" / "driver.log").read_text()


def test_the_driver_command_line_carries_the_gate_to_the_children():
    src = (PKG / "driver.py").read_text()
    assert '"--spend-cap"' in src and '"--confirm-spend"' in src and "tools.roof_eval.label" in src


# ---- the privacy audit that guards what is sent ----
def make_house(d: Path) -> Path:
    d.mkdir(parents=True)
    pts = H.gable_points(step=0.4)
    roof = np.c_[pts[:, :2] + 8.0, pts[:, 2], np.ones(len(pts))]
    gx, gy = np.meshgrid(np.arange(0, 28, 1.0), np.arange(0, 24, 1.0))
    ground = np.c_[gx.ravel(), gy.ravel(), np.zeros(gx.size), np.full(gx.size, 2.0)]
    np.save(d / "points_wide.npy", np.vstack([roof, ground]).astype(np.float32))
    ring = [(x + 8.0, y + 8.0) for x, y in H.footprint().tolist()]
    wkt = "POLYGON ((" + ", ".join(f"{x} {y}" for x, y in ring + ring[:1]) + "))"
    (d / "meta.json").write_text(json.dumps({"footprint_local_m_wkt": wkt}))
    return d


def test_forbidden_tokens_cover_id_address_zip_coordinates_and_frame_origin(tmp_path):
    house = make_house(tmp_path / "h-0000000f")
    meta = json.loads((house / "meta.json").read_text())
    meta.update(
        {
            "address": "100 Example Ave, Sampletown, CA 90000",
            "lat": 12.3456,
            "lng": -65.4321,
            "frame_x0_m": 123456.0,
            "frame_y0_m": 7654321.0,
        }
    )
    (house / "meta.json").write_text(json.dumps(meta))
    toks = make_truth.forbidden_tokens(make_truth.rv.House(house))
    for t in (
        "h-0000000f",
        "100 example ave",
        "example ave",
        "sampletown",
        "90000",
        "12.346",
        "65.432",
        "123456",
        "7654321",
    ):
        assert t in toks, t
    for leak in ("h-0000000f", "90000", "123456"):
        with pytest.raises(SystemExit, match="PRIVACY AUDIT FAILED"):
            make_truth.audit({"messages": [{"role": "user", "content": f"see {leak} here"}]}, toks, "test")
    assert make_truth.audit({"messages": [{"role": "user", "content": "x 1.0 y 2.0"}]}, toks, "test") > 0
