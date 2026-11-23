"""roof-synth against the public generator: the oracle (exact roof as result) must score ~perfect; wrong results must fail."""

import copy
import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon, box

from tools.roof_eval import m_shape, runner, synth
from tools.roof_eval.geom import load_roof

pytest.importorskip("roof_measure.engine.synth_points")
STUB = str(Path(__file__).with_name("roof_eval_stub_engine.py"))
ONLY = ["gable_d8", "hip_d16", "two_level_d8", "flat_pitched_step_d16", "complex_hip_d8", "l_shape_d4", "gable_d2"]


def cfg(tmp_path, engine, name="r"):
    return runner.Config(root=Path("."), out_dir=tmp_path / name, engine=engine, jobs=2)


@pytest.fixture(scope="module")
def oracle(tmp_path_factory):
    ok, recs, gates = synth.run(cfg(tmp_path_factory.mktemp("o"), "oracle"), ONLY)
    return ok, {r["id"]: r for r in recs}, {g["case"]: g for g in gates}


def test_oracle_scores_perfect_on_every_selected_case(oracle):
    _, recs, _ = oracle
    assert len(recs) >= 12
    for name, r in recs.items():
        m, t = r["m"], r["truth"]["T6"]
        if "trees" in name:  # canopy returns inside the wall outline + 1.2 m are reference points no facet can fit (known, shared by all engines)
            assert 0.7 <= m["fit_all"] < 0.97 and m["fit_covered"] >= 0.85, name
        else:
            assert m["fit_all"] >= 0.97 and m["coverage"] >= 0.99, name
        assert m["overlap_sqft"] < 0.5, name
        assert t["facet_iou.mean_iou"] >= 0.98 and t["flat_pitched_agreement"] >= 0.99, name
        assert abs(t["squares.err_pct"]) < 0.5 and m["false_level_change_share"] == 0, name
        for k in ("eave", "rake", "ridge", "hip", "valley", "perimeter"):
            key = f"lengths.{k}.abs_diff"
            if key in t:
                assert abs(t[key]) < max(0.01 * t[f"lengths.{k}.truth"], 0.05), (name, k)


def test_gate9_oracle_passes_dense_and_fails_the_must_refuse_density(oracle):
    ok, _, g = oracle
    assert g["gable_d8"]["pass"] and g["hip_d16"]["pass"] and g["l_shape_d4"]["pass"]
    assert not g["gable_d2"]["pass"] and not ok  # an engine that answers at 2 pts/m2 must fail gate 9


def stub(mode):
    return f"{shlex.quote(sys.executable)} {shlex.quote(STUB)} {mode} {{house_dir}} {{out_json}}"


def test_below_four_passes_only_lidar_too_sparse(tmp_path):
    ok, _, gates = synth.run(cfg(tmp_path, stub("sparse"), "a"), ["gable_d8", "gable_d2"])
    g = {x["case"]: x for x in gates}
    assert g["gable_d2"]["pass"] and not g["gable_d8"]["pass"] and not ok  # d8: no result is a failure
    for mode, name in (("refuse", "b"), ("lowdensity", "c"), ("crash", "d"), ("slow", "e")):
        _, _, gates = synth.run(runner.Config(root=Path("."), out_dir=tmp_path / name, engine=stub(mode), jobs=2, timeout_s=2), ["gable_d2"])
        assert not gates[0]["pass"], mode  # refused, low_density (the 4-6 verdict), crash and timeout all fail below 4


def test_selftest_expects_exactly_the_sparse_cases_to_fail(oracle):
    _, _, g = oracle
    assert synth.selftest_ok(list(g.values()))
    assert not synth.selftest_ok([{**next(iter(g.values())), "pass": False}])


def test_tolerances_are_data_and_floor_is_one_foot(tmp_path):
    rec = {"automation": True, "automation_ok": True, "verdict": "ok", "truth": {"T6": {
        "squares.err_pct": 0.5, "lengths.valley.truth": 8.0, "lengths.valley.abs_diff": 2.9, **SHAPE_OK}}}
    assert not synth.gate9("x_d8", 8, rec)["pass"]  # 36% of an 8 ft valley: the old 3 ft floor hid this
    assert synth.gate9("x_d8", 8, rec, {"length_floor_ft": 3.0})["pass"]
    assert synth.gate9("x_d8", 8, rec, {"length_pct": 40.0})["pass"]
    gf = tmp_path / "g.json"
    gf.write_text(json.dumps({"synth_gates": {"area_pct": 1.5, "length_floor_ft": 2.0}}))
    t = synth.tolerances(gf)
    assert t["area_pct"] == 1.5 and t["length_floor_ft"] == 2.0 and t["length_pct"] == 5.0
    assert synth.DEFAULT_TOL["length_floor_ft"] == 1.0
    assert "area_pct=2.0" in synth.tables([], [], None).splitlines()[0]


def test_truth_comes_from_totals_and_shed_high_edge_is_not_ridge():
    shed = synth._cases()["shed_d8"].roof
    t = synth.truth_dict(shed, "s")
    assert t["lengths_ft"]["ridge"] == 0.0 and t["area_sqft"] == shed.totals["area_sqft"]
    res = synth.result_dict(shed, "s")
    assert not [e for e in res["edges"] if e["type"] == "ridge"]
    ft, ovh = 3.280839895013123, 0.3
    L, W = 30 + 2 * ovh * ft, 20 + 2 * ovh * ft  # closed form: 30 x 20 ft wall plus 0.3 m overhang all round, 3/12 pitch
    k = (1 + (3 / 12) ** 2) ** 0.5
    assert shed.totals["area_sqft"] == pytest.approx(L * W * k, rel=1e-6)
    assert t["lengths_ft"]["eave"] == pytest.approx(L, rel=1e-6) and t["lengths_ft"]["rake"] == pytest.approx(2 * W * k + L, rel=1e-6)  # two side rakes plus the high edge


def test_flat_closed_form_truth():
    flat = synth._cases()["flat_d8"].roof
    t = synth.truth_dict(flat, "f")
    ft, ovh = 3.280839895013123, 0.3
    L, W = 40 + 2 * ovh * ft, 30 + 2 * ovh * ft
    assert t["area_sqft"] == pytest.approx(L * W, rel=1e-6) and t["flat_area_sqft"] == pytest.approx(L * W, rel=1e-6)
    assert t["lengths_ft"]["ridge"] == 0.0 and t["lengths_ft_extra"]["flat_edge"] == pytest.approx(2 * (L + W), rel=1e-6)


SHAPE_OK = {"facet_iou.mean_iou": 0.95, "facet_count.abs_diff": 0, "flat_pitched_agreement": 1.0}


def test_sparse_density_ok_label_with_wrong_numbers_fails():
    rec = {"automation": True, "automation_ok": True, "verdict": "ok", "truth": {"T6": {
        "squares.err_pct": 15.0, "lengths.ridge.truth": 40.0, "lengths.ridge.abs_diff": 1.0, **SHAPE_OK}}}
    assert not synth.gate9("x_d4", 4, rec)["pass"]
    assert synth.gate9("x_d4", 4, {**rec, "automation_ok": False, "verdict": "low_density"})["pass"]
    rec["truth"]["T6"]["squares.err_pct"] = 9.0
    assert synth.gate9("x_d4", 4, rec)["pass"] and not synth.gate9("x_d8", 8, rec)["pass"]
    rec["truth"]["T6"]["squares.err_pct"] = 1.0
    assert synth.gate9("x_d8", 8, rec)["pass"]
    rec["truth"]["T6"]["lengths.ridge.abs_diff"] = 4.0  # 10% of a 40 ft ridge
    assert not synth.gate9("x_d8", 8, rec)["pass"]


# ---- generator-based wrong results: each must be caught by the scorer ----
@pytest.fixture(scope="module")
def gable():
    c = synth._cases()["gable_d8"]
    roof = synth.exact_roof(c)
    return c, roof, synth.result_dict(roof, "g"), c.points()


def ref_of(pts, c):
    return pts[(pts[:, 3] != 2) & (pts[:, 2] > 1.5)][:, :3]


def score_of(res, c, pts):
    from tools.roof_eval import score

    return score.score_house(res, ref_of(pts, c), Polygon(c.roof.wall_outline), [{**synth.truth_dict(synth.exact_roof(c), "g"), "tier": "T6"}])


def test_generator_oracle_baseline(gable):
    c, _, res, pts = gable
    r = score_of(res, c, pts)
    assert r["m"]["fit_all"] > 0.97 and r["truth"]["T6"]["facet_iou.mean_iou"] > 0.98


def test_generator_one_big_facet(gable):
    c, roof, res, pts = gable
    r = copy.deepcopy(res)
    xyz = np.array([[p[0], p[1], 1.0] for f in roof.facets for p in f.xy])
    z = np.array([f.z(*p) for f in roof.facets for p in f.xy])
    a, b, cc = np.linalg.lstsq(xyz, z, rcond=None)[0]
    r["facets"] = [{"id": "f1", "polygon": [list(p) for p in roof.roof_outline], "plane": [a, b, cc], "pitch_rise": 0, "roof_type": "pitched"}]
    r["edges"] = []
    s = score_of(r, c, pts)
    assert s["m"]["fit_all"] < 0.6 and s["truth"]["T6"]["facet_iou.mean_iou"] <= 0.5
    assert s["truth"]["T6"]["facet_count.abs_diff"] == len(roof.facets) - 1


def test_generator_over_segmentation(gable):
    c, _, res, pts = gable
    r = copy.deepcopy(res)
    out = []
    for f in res["facets"]:
        poly = Polygon(f["polygon"])
        x0, y0, x1, y1 = poly.bounds
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        for k, q in enumerate((box(x0, y0, mx, my), box(mx, y0, x1, my), box(x0, my, mx, y1), box(mx, my, x1, y1))):
            piece = poly.intersection(q)
            if piece.area > 1e-6:
                out.append({**f, "id": f"{f['id']}_{k}", "polygon": [list(p) for p in piece.exterior.coords][:-1]})
    r["facets"] = out
    s = score_of(r, c, pts)
    assert s["m"]["fit_all"] > 0.97 and len(out) == 8  # planes still right: only shape and count catch it
    assert s["truth"]["T6"]["facet_iou.mean_iou"] < 0.2 and s["truth"]["T6"]["facet_count.abs_diff"] == 6


def test_generator_shifted_ridge(gable):
    c, roof, res, pts = gable
    ridge = next(e for e in roof.edges if e.type == "ridge")
    ry, rz = ridge.p0[1], ridge.p0[2]
    x0, y0, x1, y1 = Polygon(roof.roof_outline).bounds
    s_f = min(roof.facets, key=lambda f: f.polygon().centroid.y)
    n_f = max(roof.facets, key=lambda f: f.polygon().centroid.y)
    ny = ry + 1.0
    r = copy.deepcopy(res)
    ez_s, ez_n = s_f.z(0, y0), n_f.z(0, y1)
    r["facets"] = [
        {"id": "s", "polygon": [[x0, y0], [x1, y0], [x1, ny], [x0, ny]], "plane": [0, (rz - ez_s) / (ny - y0), ez_s - (rz - ez_s) / (ny - y0) * y0],
         "pitch_rise": 6, "roof_type": "pitched"},
        {"id": "n", "polygon": [[x0, ny], [x1, ny], [x1, y1], [x0, y1]], "plane": [0, -(rz - ez_n) / (y1 - ny), ez_n + (rz - ez_n) / (y1 - ny) * y1],
         "pitch_rise": 6, "roof_type": "pitched"}]
    s = score_of(r, c, pts)
    assert s["m"]["fit_all"] < 0.9 and s["truth"]["T6"]["facet_iou.mean_iou"] < 0.9
    assert s["m"]["coverage"] > 0.95  # shape right, heights wrong


def test_oracle_result_validates_against_exact_totals(gable):
    _, roof, res, _ = gable
    roof_r = load_roof(res)
    assert m_shape.flat_pitched(roof_r)["area_sqft"] == pytest.approx(roof.totals["area_sqft"], rel=1e-6)
    assert json.dumps(res)


def test_high_edge_is_rake_and_flagged():
    shed = synth.result_dict(synth._cases()["shed_d8"].roof, "s")
    roof = load_roof(shed)
    from tools.roof_eval import edges_re

    rc = edges_re.recompute(roof, np.zeros((0, 3)))
    high = [e for e in rc.edges if e.high_edge]
    assert len(high) == 1 and high[0].type == "rake" and high[0].length_ft == pytest.approx(31.97, abs=0.1)
    assert {e.type for e in rc.edges} == {"eave", "rake"}  # never ridge


def test_synthetic_truth_uses_drawn_geometry_and_reports_the_priced_shortfall(tmp_path):
    c = synth._cases()["gable_d16"]
    res = synth.result_dict(synth.exact_roof(c), "g")
    res["totals"] = {"planes_surface_area_sqft": c.roof.totals["area_sqft"] * 0.95, "outline_perimeter_ft": c.roof.totals["perimeter_ft"] * 0.9}
    from tools.roof_eval import score

    t6 = {**synth.truth_dict(synth.exact_roof(c), "g"), "tier": "T6"}
    pts = c.points()
    ref = pts[(pts[:, 3] != 2) & (pts[:, 2] > 1.5)][:, :3]
    r = score.score_house(res, ref, Polygon(c.roof.wall_outline), [t6, {**t6, "source": "vendor_report", "tier": "T1"}])
    d, v = r["truth"]["T6"], r["truth"]["T1"]
    assert abs(d["squares.err_pct"]) < 0.1 and d["squares.priced_ratio"] == pytest.approx(0.95, abs=1e-3)  # drawn vs exact; priced shortfall visible
    assert v["squares.err_pct"] == pytest.approx(-5.0, abs=0.1) and v["squares.err_pct_drawn"] == pytest.approx(0, abs=0.1)  # vendor: priced basis
    assert abs(d["lengths.perimeter.err_pct"]) < 0.5 and v["lengths.perimeter.err_pct"] == pytest.approx(-10.0, abs=0.5)
