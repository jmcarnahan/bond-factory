"""Every building on the lot: the optional ``other_buildings`` key and ``lot_*`` totals. Offline, synthetic."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import FIXTURES
from shapely.geometry import Polygon

from roof_measure import _isolate, cache, library, lot
from roof_measure.blocks import BlocksError
from roof_measure.classify import BlockSet
from roof_measure.deadline import Deadline
from roof_measure.footprint_types import Footprint
from roof_measure.library import measure
from roof_measure.pipeline import run_pipeline
from roof_measure.pipeline_notes import collect_warnings

ADDR = "100 Example Ave, Sampletown, CA 90000"
BLOCKS = FIXTURES / "site1_blocks.json"
FT_PER_M = 1 / 0.3048


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(cache, "_send", boom)


def cand(i="B2", area=424.0):
    return lot.Candidate(Polygon([(0, 0), (1, 0), (1, 1)]), "lacounty_lariac_2020", i, area)


def builder_at(dx_m: float, dy_m: float, calls: list | None = None):
    """A stand-in for ``lot.build_blocks``: the fixture's blocks in a frame shifted by (dx_m, dy_m) from the main one."""
    def build(c, main_frame, address, out_path):
        if calls is not None:
            calls.append(c.id)
        d = json.loads(BLOCKS.read_text())
        d["frame"] = {**d["frame"], "x0_m": d["frame"]["x0_m"] + dx_m, "y0_m": d["frame"]["y0_m"] + dy_m}
        Path(out_path).write_text(json.dumps(d))
        return BlockSet.load(out_path)
    return build


def call(tmp_path, **kw):
    args = {"method": "lidar_skeleton", "verify": False, "cache_dir": tmp_path / "cache", "blocks_path": BLOCKS,
            "isolate": False}
    return measure(ADDR, **(args | kw))


def model_of(env):
    return {k: v for k, v in env["model"].items() if k != "generated_at"}


def _strip(v):
    if isinstance(v, dict):
        return {k: _strip(x) for k, x in v.items() if k != "generated_at"}
    return [_strip(x) for x in v] if isinstance(v, list) else v


def stable(env):
    return json.dumps(_strip(env), sort_keys=True)


def test_default_call_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: pytest.fail("looked for buildings"))
    plain = call(tmp_path)
    assert "other_buildings" not in plain and not any(k.startswith("lot_") for k in plain["totals"])
    assert stable(call(tmp_path, include_other_buildings=False)) == stable(plain)


def test_asking_with_no_other_building_changes_nothing(tmp_path):
    assert stable(call(tmp_path, include_other_buildings=True)) == stable(call(tmp_path))  # blocks_path: no lookup


def test_two_building_lot_has_the_key_offset_and_totals(tmp_path, monkeypatch):
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: [cand("B2", 424.0)])
    monkeypatch.setattr(lot, "build_blocks", builder_at(10.0, 20.0))
    env = call(tmp_path, include_other_buildings=True)
    plain = call(tmp_path)
    (other,) = env["other_buildings"]
    assert other["index"] == 1 and other["status"] in ("ok", "planes_only") and other["error_code"] is None
    assert other["footprint"] == {"provider": "lacounty_lariac_2020", "id": "B2", "area_sqft": 424.0}
    assert other["offset_ft"] == pytest.approx([10.0 * FT_PER_M, 20.0 * FT_PER_M], abs=0.01)
    assert set(other["model"]) >= {"facets", "totals", "quality", "planes"} and set(plain["totals"]) <= set(other["totals"])
    t = env["totals"]
    assert t["lot_buildings"] == 2
    assert t["lot_area_sqft"] == pytest.approx(plain["totals"]["area_sqft"] + other["totals"]["area_sqft"], abs=0.01)
    assert t["lot_squares"] == pytest.approx(plain["totals"]["squares"] + other["totals"]["squares"], abs=0.01)
    assert t["lot_outline_perimeter_ft"] == pytest.approx(
        plain["totals"]["outline_perimeter_ft"] + other["totals"]["outline_perimeter_ft"], abs=0.01)
    for k, v in plain["totals"].items():  # the existing keys still mean "the main building"
        assert t[k] == v
    assert model_of(env) == model_of(plain) and env["warnings"] == plain["warnings"]
    json.dumps(env, allow_nan=False)


def test_offset_is_east_north_of_the_main_origin():
    main = {"epsg": 32611, "x0_m": 100.0, "y0_m": 200.0}
    assert lot.offset_ft(main, {**main, "x0_m": 103.048, "y0_m": 197.0}) == [10.0, -9.84]
    with pytest.raises(ValueError):
        lot.offset_ft(main, {**main, "epsg": 32612})


def test_a_shed_under_120_sqft_is_ignored(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: [cand("SHED", 119.0)])
    monkeypatch.setattr(lot, "build_blocks", builder_at(5.0, 5.0, calls))
    env = call(tmp_path, include_other_buildings=True)
    assert calls == [] and "other_buildings" not in env and "lot_buildings" not in env["totals"]


def test_the_old_warning_for_other_buildings_stays():
    fpinfo = {"source": "lariac", "warnings": [], "codes": [], "other_buildings": 1}
    _, codes = collect_warnings({"warnings": [], "source": {}}, fpinfo, {"verdict": "unverified"}, None, None,
                                "lidar_skeleton", [])
    assert "other_buildings_on_parcel" in codes


def test_candidates_come_from_the_footprint_chain_largest_first(monkeypatch):
    from roof_measure import footprint

    fp = Footprint(provider="lacounty_lariac_2020", id="MAIN", polygon_wgs84=Polygon([(0, 0), (1, 0), (1, 1)]),
                   height_ft=None, area_sqft=2000.0, parcel_id="1",
                   other_buildings=[Polygon([(0, 0), (1, 0), (1, 1)]), Polygon([(0, 0), (2, 0), (2, 2)])],
                   other_info=[{"id": "S", "area_sqft": 90.0}, {"id": "G", "area_sqft": 424.0}])
    monkeypatch.setattr(footprint, "fetch_footprint", lambda *a, **k: fp)
    res = SimpleNamespace(footprint_source="lariac",
                          blockset=SimpleNamespace(footprint_meta={"id": "MAIN", "provider": "lacounty_lariac_2020"}))
    got = lot.find_candidates(res, ADDR, (33.0, -118.0), Deadline.after(60))
    assert [c.id for c in got] == ["G", "S"] and got[0].area_sqft == 424.0
    res.blockset.footprint_meta["id"] = "OTHER"  # the chain answered with a different building: nothing
    assert lot.find_candidates(res, ADDR, (33.0, -118.0), Deadline.after(60)) == []


def test_a_failing_second_building_is_recorded_and_the_main_result_is_intact(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise BlocksError("no roof here")
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: [cand("B2", 424.0)])
    monkeypatch.setattr(lot, "build_blocks", boom)
    env = call(tmp_path, include_other_buildings=True)
    plain = call(tmp_path)
    (other,) = env["other_buildings"]
    assert other["status"] == "failed" and other["error_code"] == "measurement_failed"
    assert other["model"] is None and other["totals"] is None and other["offset_ft"] is None
    assert model_of(env) == model_of(plain)
    assert env["totals"]["lot_buildings"] == 1 and env["totals"]["lot_area_sqft"] == plain["totals"]["area_sqft"]
    assert env["warning_codes"][-1] == "other" and "could not be measured" in env["warnings"][-1]


def test_one_failure_does_not_stop_the_next_building(tmp_path, monkeypatch):
    ok = builder_at(8.0, 8.0)

    def build(c, main_frame, address, out_path):
        if c.id == "BAD":
            raise BlocksError("x")
        return ok(c, main_frame, address, out_path)
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: [cand("BAD", 500.0), cand("GOOD", 300.0)])
    monkeypatch.setattr(lot, "build_blocks", build)
    env = call(tmp_path, include_other_buildings=True)
    assert (env["other_buildings"][0]["index"], env["other_buildings"][0]["status"]) == (1, "failed")
    assert env["other_buildings"][1]["status"] in ("ok", "planes_only") and env["totals"]["lot_buildings"] == 2


class _Clock:
    """A deadline whose remaining time is scripted (the real one is wall-clock)."""

    def __init__(self, *left):
        self.left = list(left)

    def remaining(self):
        return self.left.pop(0) if len(self.left) > 1 else self.left[0]

    def expired(self):
        return False

    def check(self, stage):
        return None

    def timeout(self, cap):
        return cap


def test_deadline_exhaustion_skips_the_rest_and_says_so(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(lot, "build_blocks", builder_at(6.0, 6.0, calls))
    work = tmp_path / "w"
    res = run_pipeline(ADDR, work, blocks_path=BLOCKS, verify=False, render=False)
    cands = [cand("A", 500.0), cand("B", 400.0), cand("C", 300.0)]
    # first share 60 / 3 = 20 s (measured); then 4 s left for two buildings: below MIN_SHARE_S, both skipped
    lot.add_other_buildings(res, address=ADDR, lat_lng=None, deadline=_Clock(60.0, 4.0), out_dir=work,
                            finder=lambda *a, **k: cands)
    entries = res.envelope["other_buildings"]
    assert calls == ["A"]
    assert entries[0]["status"] in ("ok", "planes_only")
    assert [(e["status"], e["error_code"]) for e in entries[1:]] == [("failed", "timeout")] * 2
    assert res.envelope["totals"]["lot_buildings"] == 2
    assert "timeout" in res.envelope["warnings"][-1]


def test_a_crashed_child_is_retried_without_the_extra_buildings(tmp_path, monkeypatch):
    seen: list[bool] = []

    def fake(req, on_stage, grace=0):
        seen.append(bool(req["include_other_buildings"]))
        if req["include_other_buildings"]:
            raise _isolate.ChildCrashed("measurement_failed", "the measurement process exited with code -11")
        return {"warnings": ["w"], "warning_codes": ["other"], "totals": {}}
    monkeypatch.setattr(_isolate, "run_isolated", fake)
    env = measure(ADDR, method="lidar_skeleton", verify=False, cache_dir=tmp_path / "c", blocks_path=BLOCKS,
                  include_other_buildings=True)
    assert seen == [True, False]
    assert env["warning_codes"][-1] == "other" and "other buildings" in env["warnings"][-1]
    seen.clear()
    with pytest.raises(library.MeasureError):  # without the flag a crash is still a crash (non-agent method)
        monkeypatch.setattr(_isolate, "run_isolated", lambda *a, **k: (_ for _ in ()).throw(
            _isolate.ChildCrashed("measurement_failed", "x")))
        measure(ADDR, method="lidar_skeleton", verify=False, cache_dir=tmp_path / "c", blocks_path=BLOCKS)


def test_an_agent_crash_with_extra_buildings_still_falls_back_to_the_rules(tmp_path, monkeypatch):
    """The agent crashes with and without the extra buildings: the third try is the rule method, not an error."""
    seen: list[tuple[str, bool]] = []

    def fake(req, on_stage, grace=0):
        seen.append((req["method"], bool(req["include_other_buildings"])))
        if req["method"] == "lidar_agent":
            raise _isolate.ChildCrashed("measurement_failed", "the measurement process exited with code -11")
        return {"warnings": [], "warning_codes": [], "totals": {}, "model": {"quality": {"reasons": []}}}
    monkeypatch.setattr(_isolate, "run_isolated", fake)
    env = measure(ADDR, method="lidar_agent", verify=False, cache_dir=tmp_path / "c", blocks_path=BLOCKS,
                  include_other_buildings=True)
    assert seen == [("lidar_agent", True), ("lidar_agent", False), ("lidar_skeleton", False)]
    assert env["warning_codes"] == ["agent_failed_fell_back", "other"]


def test_work_files_do_not_collide(tmp_path, monkeypatch):
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: [cand("A", 500.0), cand("B", 300.0)])
    monkeypatch.setattr(lot, "build_blocks", builder_at(6.0, 6.0))
    work = tmp_path / "keep"
    call(tmp_path, include_other_buildings=True, work_dir=work)
    assert (work / "lot_1" / "blocks.json").is_file() and (work / "lot_2" / "blocks.json").is_file()
    shutil.rmtree(work)


def _ok_entry(index, totals, model=None):
    return {"index": index, "footprint": {"provider": "p", "id": str(index), "area_sqft": 300.0}, "offset_ft": [1.0, 2.0],
            "status": "ok", "error_code": None, "model": model or {"source": {}}, "totals": totals}


def test_a_building_with_nan_totals_is_failed_and_the_lot_totals_stay_finite(tmp_path, monkeypatch):
    bad = {"area_sqft": float("nan"), "squares": 3.0, "outline_perimeter_ft": 70.0}
    good = {"area_sqft": 300.0, "squares": 3.0, "outline_perimeter_ft": 70.0}
    monkeypatch.setattr(lot, "find_candidates", lambda *a, **k: [cand("BAD", 500.0), cand("GOOD", 300.0)])
    monkeypatch.setattr(lot, "measure_one", lambda i, *a, **k: _ok_entry(i, bad if i == 1 else good))
    env = call(tmp_path, include_other_buildings=True)
    plain = call(tmp_path)
    assert model_of(env) == model_of(plain)
    first, second = env["other_buildings"]
    assert first["status"] == "failed" and first["error_code"] == "measurement_failed" and first["totals"] is None
    assert second["status"] == "ok" and env["totals"]["lot_buildings"] == 2
    assert env["totals"]["lot_area_sqft"] == pytest.approx(plain["totals"]["area_sqft"] + 300.0, abs=0.01)
    assert json.dumps(env, allow_nan=False)  # nothing non-finite reached the envelope
    assert "other" in env["warning_codes"]


def test_a_nan_inside_a_building_s_model_fails_that_building_only(tmp_path, monkeypatch):
    from roof_measure import pipeline

    main = BlockSet.load(BLOCKS)
    env = {"model": {"source": {}, "facets": [{"area_sqft": float("nan")}]},
           "totals": {"area_sqft": 300.0, "squares": 3.0, "outline_perimeter_ft": 70.0}}
    monkeypatch.setattr(pipeline, "run_pipeline", lambda *a, **k: SimpleNamespace(envelope=env))
    got = lot.measure_one(1, cand("B2", 424.0), main.frame, {"formatted": "x"}, tmp_path, Deadline.after(30_000),
                          builder=lambda c, f, a, p: SimpleNamespace(frame=main.frame))
    assert got["status"] == "failed" and got["error_code"] == "measurement_failed" and got["model"] is None


def test_attaching_the_lot_never_raises_and_writes_no_lot_keys_on_failure(monkeypatch):
    env = {"totals": {"area_sqft": float("nan"), "squares": 1.0, "outline_perimeter_ft": 1.0}, "warnings": [],
           "warning_codes": []}
    res = SimpleNamespace(envelope=env, blockset=SimpleNamespace(frame={}, address={}))
    monkeypatch.setattr(lot, "measure_one", lambda i, *a, **k: _ok_entry(i, {"area_sqft": 1.0, "squares": 1.0}))
    lot.add_other_buildings(res, address="x", lat_lng=None, deadline=Deadline.after(60_000), out_dir=".",
                            finder=lambda *a, **k: [cand("B2", 424.0)])
    assert not any(k.startswith("lot_") for k in env["totals"]) and "other_buildings" not in env
    assert env["warning_codes"] == ["other"]
