"""The roof-eval harness end to end on a tiny synthetic data root: run, score, gates, baselines, determinism, sweep."""

import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pytest
import roof_eval_helpers as H

from tools.roof_eval import (
    adapter_library,
    adapter_results,
    baseline,
    blind,
    blind_score,
    cli,
    data,
    gates,
    runner,
    sweep,
)

STUB = str(Path(__file__).with_name("roof_eval_stub_engine.py"))
RULES = Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "price_rules.example.json"


def engine(mode):
    return f"{shlex.quote(sys.executable)} {shlex.quote(STUB)} {mode} {{house_dir}} {{out_json}}"


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "data"
    H.build_root(r, n=4)
    return r


def cfg_for(root, tmp_path, mode, name="run", **kw):
    return runner.Config(root=root, out_dir=tmp_path / name, engine=engine(mode), split="all", jobs=2,
                         price_rules=RULES, **kw)


def test_data_root_error_is_clear(monkeypatch):
    monkeypatch.delenv("ROOF_EVAL_DATA", raising=False)
    with pytest.raises(data.DataError, match="ROOF_EVAL_DATA"):
        data.data_root(None)


def test_perfect_engine_run_writes_outputs_and_scores_clean(root, tmp_path):
    s = runner.evaluate(cfg_for(root, tmp_path, "perfect"))
    out = tmp_path / "run"
    assert {p.name for p in out.iterdir()} >= {"per_house.jsonl", "summary.json", "tables.md", "results"}
    o = s["overall"]
    assert s["n"] == 4 and o["automation_rate"] == 1.0
    assert o["median"]["fit_all"] > 0.97 and o["median"]["coverage"] == 1.0 and o["overlap_houses"] == 0
    assert o["T2_facet_iou_mean"] == pytest.approx(1.0) and o["T2_n"] == 4
    assert s["t3"]["n"] == 4 and s["t3"]["median_ratio"] == pytest.approx(1.1553, abs=2e-3)
    assert "by" in s and s["by"]["roof_class"]["pitched"]["n"] == 4
    recs = [json.loads(ln) for ln in (out / "per_house.jsonl").read_text().splitlines()]
    assert [r["id"] for r in recs] == sorted(r["id"] for r in recs)
    assert "ALL" in (out / "tables.md").read_text()


def test_reference_points_are_derived_once_and_frozen(root, tmp_path):
    hd = root / "houses" / "h-00000000"
    ref1 = data.reference_points(hd)
    stamp = (hd / "reference_points.npy").stat().st_mtime_ns
    ref2 = data.reference_points(hd)
    assert (hd / "reference_points.npy").stat().st_mtime_ns == stamp and np.array_equal(ref1, ref2)
    assert json.loads((hd / "reference_points.json").read_text())["rule"] == data.REF_RULE
    assert len(ref1) > 100 and ref1[:, 2].min() > 2.9  # roof points only: ground (z = 0) is excluded


def test_reference_rule_ignores_ground_vegetation_and_far_points():
    w = np.array([[1, 1, 5, 1], [1, 1, 5, 5], [1, 1, 0, 2], [2, 2, 0, 2], [3, 3, 0, 2], [4, 4, 0, 2], [5, 5, 0, 2], [6, 6, 0, 2],
                  [1, 1, 1.0, 1], [50, 50, 5, 1]], float)
    foot = data.parse_polygon([[0, 0], [4, 0], [4, 4], [0, 4]])
    ref = data.derive_reference(w, foot)
    assert ref.tolist() == [[1, 1, 5]]  # vegetation (class 5), ground, a 1 m high return and a far return are all out


def test_refuse_everything_fails_the_automation_gate(root, tmp_path):
    spec = {"gates": [{"name": "automation", "metric": "automation_ok", "agg": "rate", "op": ">=", "value": 0.9}]}
    gf = tmp_path / "gates.json"
    gf.write_text(json.dumps(spec))
    ok = runner.evaluate(cfg_for(root, tmp_path, "perfect", "a", gates_file=gf))
    bad = runner.evaluate(cfg_for(root, tmp_path, "refuse", "b", gates_file=gf))
    assert ok["ok"] is True and ok["gates"][0]["value"] == 1.0
    assert bad["ok"] is False and bad["gates"][0]["value"] == 0.0 and bad["overall"]["n_result"] == 0


def test_poor_verdict_is_not_automation_ok(root, tmp_path):
    s = runner.evaluate(cfg_for(root, tmp_path, "poor"))
    assert s["overall"]["n_result"] == 4 and s["overall"]["n_ok"] == 0 and s["overall"]["verdicts"] == {"poor_fit": 4}


def test_crashing_engine_is_a_recorded_failure_not_a_crash(root, tmp_path):
    s = runner.evaluate(cfg_for(root, tmp_path, "crash"))
    assert s["overall"]["failures"] == {"failed": 4}
    assert "engine exploded" in (tmp_path / "run" / "tables.md").read_text()


def test_timeout_is_recorded(root, tmp_path):
    c = cfg_for(root, tmp_path, "slow", timeout_s=1, limit=1)
    assert runner.evaluate(c)["overall"]["failures"] == {"timeout": 1}


def test_gate_aggregations_and_populations(root, tmp_path):
    runner.evaluate(cfg_for(root, tmp_path, "perfect"))
    recs = [json.loads(ln) for ln in (tmp_path / "run" / "per_house.jsonl").read_text().splitlines()]
    spec = {"gates": [
        {"name": "fit share", "metric": "fit_covered", "agg": "share", "pred": {"op": ">=", "value": 0.8}, "op": ">=", "value": 1.0,
         "require": ["automation_ok"]},
        {"name": "median facets", "metric": "facets", "agg": "median", "op": "==", "value": 2},
        {"name": "negatives only", "metric": "automation_ok", "agg": "rate", "where": ["split=negative"], "op": "<=", "value": 0.0},
        {"name": "too few", "metric": "facets", "agg": "max", "where": ["split=negative"], "min_n": 5, "op": ">=", "value": 0},
        {"name": "too few but skipped", "metric": "facets", "agg": "max", "where": ["split=tuning"], "min_n": 99,
         "on_insufficient": "skip", "op": ">=", "value": 0},
        {"name": "T2 iou", "metric": "truth.T2.facet_iou.mean_iou", "agg": "median", "op": ">=", "value": 0.99},
        {"name": "count", "metric": "automation", "agg": "count", "where": ["split!=negative"], "op": "==", "value": 3}]}
    r = {g["name"]: g for g in gates.evaluate(spec, recs)}
    assert r["fit share"]["passed"] and r["median facets"]["passed"] and r["T2 iou"]["passed"] and r["count"]["passed"]
    assert r["negatives only"]["n"] == 1 and not r["negatives only"]["passed"]  # the perfect engine "labels good" a negative house
    assert not r["too few"]["passed"] and "insufficient" in r["too few"]["note"]
    assert r["too few but skipped"]["passed"]


def test_baseline_needs_confirm_and_compare_flags_regressions(root, tmp_path):
    runner.evaluate(cfg_for(root, tmp_path, "perfect", "good"))
    bdir = root / "baselines" / "b1"
    with pytest.raises(SystemExit, match="CONFIRM=1"):
        baseline.freeze(tmp_path / "good", bdir, False)
    baseline.freeze(tmp_path / "good", bdir, True, root / "manifest.json")
    meta = json.loads((bdir / "metrics.json").read_text())
    assert len(meta["per_house"]) == 4 and all(len(v["sha256"]) == 64 for v in meta["per_house"].values())
    same = runner.evaluate(cfg_for(root, tmp_path, "perfect", "same", baseline="b1"))
    assert same["compare"]["pass"] and same["compare"]["n_flagged"] == 0 and same["ok"]
    for mode, why in (("bigfacet", "area"), ("overlap", "overlap"), ("flatswap", "fit_all")):
        c = runner.evaluate(cfg_for(root, tmp_path, mode, mode, baseline="b1"))
        assert not c["compare"]["pass"] and c["compare"]["n_flagged"] == 4 and not c["ok"], mode
        assert why in str(c["compare"]["reasons"]), (mode, c["compare"]["reasons"])
    lost = runner.evaluate(cfg_for(root, tmp_path, "refuse", "lost", baseline="b1"))
    assert lost["compare"]["reasons"] == {"lost_result": 4}
    baseline.freeze(tmp_path / "good", bdir, True)  # re-freeze moves the old one aside, never deletes it
    assert any(p.name.startswith("b1.replaced-") for p in (root / "baselines").iterdir())


def test_compare_ignores_houses_missing_from_baseline_and_fails_when_nothing_pairs(root, tmp_path):
    runner.evaluate(cfg_for(root, tmp_path, "perfect", "good"))
    bdir = root / "baselines" / "b2"
    baseline.freeze(tmp_path / "good", bdir, True)
    for f in list((bdir / "results").iterdir()):
        f.unlink()
    c = runner.evaluate(cfg_for(root, tmp_path, "perfect", "x", baseline="b2"))["compare"]
    assert c["n_paired"] == 0 and not c["pass"]


def test_twice_identical_for_deterministic_and_different_for_random(root, tmp_path):
    same, d1, d2, _ = runner.check_twice(cfg_for(root, tmp_path, "perfect", "t1"))
    assert same and d1 == d2
    same, d1, d2, _ = runner.check_twice(cfg_for(root, tmp_path, "random", "t2"))
    assert not same


def test_split_and_where_selection(root):
    rows = data.load_manifest(root)
    assert len(data.select_rows(rows, "tuning")) == 3 and len(data.select_rows(rows, "negative")) == 1
    assert len(data.select_rows(rows, "all", ["roof_class=pitched"])) == 4
    assert data.select_rows(rows, "all", ["roof_class!=pitched"]) == []
    rows[0]["flags"] = ["derived_thin"]
    assert len(data.select_rows(rows, "all", ["flags!=derived_thin"])) == 3
    rows[1]["flags"] = ["canary"]
    assert [r["id"] for r in data.select_rows(rows, "demo")] == [rows[1]["id"]]
    assert data.select_rows([{**rows[0], "split": "excluded"}], "all") == []


def test_pooled_stratum():
    assert data.pooled_stratum({"roof_class": "pitched"}) == "pitched"
    assert data.pooled_stratum({"roof_class": "tile"}) == "pitched"
    assert data.pooled_stratum({"roof_class": "mixed"}) == "flat+mixed"
    assert data.pooled_stratum({"roof_class": "pitched", "complexity": "complex(>=10)"}) == "complex"
    assert data.pooled_stratum({"roof_class": "shingle_pitched", "complexity": "medium(5-9)"}) == "pitched"
    assert data.tier_of("llm_vision_api") == "T2" and data.tier_of("vendor_report") == "T1" and data.tier_of("contractor_squares") == "T3"
    assert data.pooled_stratum({"roof_class": "commercial"}) == "flat+mixed"  # plan 3.7a: commercial is flat+mixed unless complex
    assert data.pooled_stratum({"roof_class": "commercial", "complexity": "complex(>=10)"}) == "complex"


def _lib_env():
    ft = 1 / 0.3048
    return {"pipeline_version": "0.4.0", "model": {
        "facets": [{"id": "f1", "block": "b1", "polygon": [[0, 0], [12 * ft, 0], [12 * ft, 4 * ft], [0, 4 * ft]], "pitch_rise": 6.0, "aspect_deg": 180.0},
                   {"id": "f2", "block": "b2", "polygon": [[0, 4 * ft], [12 * ft, 4 * ft], [12 * ft, 8 * ft], [0, 8 * ft]], "pitch_rise": 6.0, "aspect_deg": 0.0}],
        "blocks": [{"id": "b1", "polygon": [[0, 0], [12 * ft, 0], [12 * ft, 4 * ft], [0, 4 * ft]], "eave_height_ft": 3.0 * ft},
                   {"id": "b2", "polygon": [[0, 4 * ft], [12 * ft, 4 * ft], [12 * ft, 8 * ft], [0, 8 * ft]], "eave_height_ft": 3.0 * ft}],
        "edges": [{"type": "ridge", "points": [[0, 4 * ft], [12 * ft, 4 * ft]], "facets": ["f1", "f2"]},
                  {"type": "parapet", "points": [[0, 0], [12 * ft, 0]], "facets": ["f1"]}],
        "planes": []}, "totals": {"area_sqft": 1155.0}}


def _lib_run(root, tmp_path, env, name, engine_name="library"):
    (root / "houses" / "h-00000000" / "envelope.json").write_text(json.dumps(env))
    s = runner.evaluate(runner.Config(root=root, out_dir=tmp_path / name, engine=engine_name, split="all", limit=1, jobs=1))
    return s, json.loads((tmp_path / name / "results" / "h-00000000.json").read_text())


def test_library_adapter_eave_datum_one_constant_per_building_no_per_facet_refit(root, tmp_path):
    env = _lib_env()
    s, r = _lib_run(root, tmp_path, env, "lib")
    assert r["diagnostics"]["datum"] == ["eave_height"] and s["overall"]["median"]["fit_all"] > 0.97
    assert {e["type"] for e in r["edges"]} == {"ridge", "flat_edge"}  # parapet is flat_edge; the ridge's z comes from both facets
    # a wrong eave height on BOTH blocks is a building-wide offset: the single constant absorbs it
    for b in env["model"]["blocks"]:
        b["eave_height_ft"] = 1.0 / 0.3048
    assert _lib_run(root, tmp_path, env, "lib2")[0]["overall"]["median"]["fit_all"] > 0.97
    # a wrong height on ONE block is not rescued by any refit
    env["model"]["blocks"][1]["eave_height_ft"] = 2.0 / 0.3048
    s3, _ = _lib_run(root, tmp_path, env, "lib3")
    assert s3["overall"]["median"]["fit_all"] < 0.7


def test_library_ground_datum_uses_the_ground_ring_not_roof_points(root, tmp_path):
    env = _lib_env()
    s, r = _lib_run(root, tmp_path, env, "g1", "library:ground")
    assert abs(r["diagnostics"]["building_shift_m"]) < 0.05 and s["overall"]["median"]["fit_all"] > 0.97
    for b in env["model"]["blocks"]:
        b["eave_height_ft"] = 1.0 / 0.3048  # ground datum cannot absorb a wrong eave height
    assert _lib_run(root, tmp_path, env, "g2", "library:ground")[0]["overall"]["median"]["fit_all"] < 0.2


def test_library_adapter_matches_model_planes_by_overlap(root, tmp_path):
    env = _lib_env()
    ft = 1 / 0.3048
    # model plane polygons slightly different from the facets (cleaned facets): the plane_eq is still found
    env["model"]["planes"] = [{"polygon": [[0.2, 0.2], [12 * ft, 0.2], [12 * ft, 4 * ft], [0.2, 4 * ft]], "plane_eq": [0.5, 0.0, 3.0 * ft]}]
    _, r = _lib_run(root, tmp_path, env, "m1")
    assert sorted(f["datum"] for f in r["facets"]) == ["eave_height", "plane_eq"]


def test_library_adapter_prefers_plane_eq_and_refuses_empty(root, tmp_path):
    hd = root / "houses" / "h-00000001"
    ft = 1 / 0.3048
    env = {"model": {"facets": [{"id": "f1", "polygon": [[0, 0], [12 * ft, 0], [12 * ft, 4 * ft], [0, 4 * ft]], "pitch_rise": 6.0,
                                 "aspect_deg": 180.0, "plane_eq": [0.5, 0.0, 0.0]}], "blocks": [], "edges": []}}
    (hd / "envelope.json").write_text(json.dumps(env))
    r = adapter_library.convert(hd)
    assert r["facets"][0]["plane"][:2] == [0.5, 0.0] and r["diagnostics"]["datum"] == ["plane_eq"]
    (hd / "envelope.json").write_text(json.dumps({"model": {"facets": []}}))
    assert adapter_library.convert(hd)["diagnostics"]["quality"]["verdict"] == "refused"


def test_results_dir_adapter_with_slug_map_and_step_alias(root, tmp_path):
    rd = tmp_path / "research"
    (rd / "some-slug").mkdir(parents=True)
    res = H.gable_result()
    res["edges"].append(H.edge("step", (6, 0.5, 3.25), (6, 3.5, 4.75), ["f1"]))
    (rd / "some-slug" / "result.json").write_text(json.dumps(res))
    sm = tmp_path / "map.json"
    sm.write_text(json.dumps({"h-00000000": {"slug": "some-slug", "address": "x"}}))
    out = tmp_path / "o.json"
    assert adapter_results.main([str(root / "houses" / "h-00000000"), str(out), "--results-dir", str(rd), "--slug-map", str(sm)]) == 0
    assert any(e["type"] == "level_change" for e in json.loads(out.read_text())["edges"])
    assert adapter_results.main([str(root / "houses" / "h-00000001"), str(out), "--results-dir", str(rd)]) == 3


def test_cli_exit_codes(root, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROOF_EVAL_OUT", str(tmp_path / "out"))
    base = ["eval", "--data", str(root), "--split", "all", "--engine", engine("perfect"), "--jobs", "2"]
    assert cli.main([*base, "--no-gates"]) == 0
    gf = tmp_path / "g.json"
    gf.write_text(json.dumps({"gates": [{"name": "x", "metric": "fit_all", "agg": "median", "op": ">=", "value": 1.5}]}))
    assert cli.main([*base, "--gates", str(gf)]) == 1
    assert cli.main(["eval", "--data", str(tmp_path / "nope")]) == 2
    assert cli.main([*base, "--twice", "--no-gates"]) == 0
    assert cli.main(["baseline", "--data", str(root), "--name", "z"]) == 2  # no CONFIRM
    assert cli.main(["baseline", "--data", str(root), "--name", "z", "--confirm"]) == 0
    assert (root / "baselines" / "z" / "metrics.json").is_file()
    capsys.readouterr()


def test_sweep_is_truth_free_and_writes_nothing_into_house_dirs(root, tmp_path):
    hs = tmp_path / "sweep_houses"
    for k, hid in enumerate(["s-1", "s-2", "s-3"]):
        src = root / "houses" / f"h-{k:08x}"
        d = hs / hid
        d.mkdir(parents=True)
        for f in ("points.npy", "points_wide.npy", "footprint.json", "meta.json"):
            (d / f).write_bytes((src / f).read_bytes())
    c = runner.Config(root=Path("."), out_dir=tmp_path / "sw", engine=engine("perfect"), jobs=2)
    s = sweep.sweep(c, hs)
    assert s["n"] == 3 and s["overall"]["automation_rate"] == 1.0 and s["overall"]["parcel_match"] == {"exact": 3}
    assert not (hs / "s-1" / "reference_points.npy").exists()
    c2 = runner.Config(root=Path("."), out_dir=tmp_path / "sw2", engine=engine("crash"), jobs=2)
    s2 = sweep.sweep(c2, hs)
    assert s2["overall"]["failures"] == {"failed": 3} and "boom: engine exploded" in s2["error_classes"]


def test_blind_draw_renders_and_key_stays_apart(root, tmp_path):
    for name, mode in (("a", "perfect"), ("b", "bigfacet")):
        runner.evaluate(cfg_for(root, tmp_path, mode, name))
    rows = data.select_rows(data.load_manifest(root), "all")
    out, key = tmp_path / "imgs", tmp_path / "keys" / "key.json"
    k = blind.make(root, rows, [f"lib={tmp_path / 'a' / 'results'}", f"raster={tmp_path / 'b' / 'results'}"], 3, 7, out, key)
    assert len(k["houses"]) == 3 and sorted(p.name for p in out.glob("*.png")) == ["H001.png", "H002.png", "H003.png"]
    assert key.is_file() and not (out / "key.json").exists()
    assert "lib" not in (out / "manifest.json").read_text() and "h-0" not in (out / "manifest.json").read_text()
    for h in k["houses"].values():
        assert {h["X"], h["Y"]} == {"lib", "raster"}
    again = blind.make(root, rows, [f"lib={tmp_path / 'a' / 'results'}", f"raster={tmp_path / 'b' / 'results'}"], 3, 7,
                       tmp_path / "imgs2", tmp_path / "keys" / "key2.json")
    assert again == k  # same seed, same draw and same letters
    with pytest.raises(SystemExit, match="outside"):
        blind.make(root, rows, [f"a={tmp_path / 'a' / 'results'}", f"b={tmp_path / 'b' / 'results'}"], 1, 1, out, out / "key.json")
    with pytest.raises(SystemExit, match="2 or 3"):
        blind.make(root, rows, ["a=x"], 1, 1, out, key)


def test_blind_draw_is_stratified():
    rows = ([{"id": f"p{i}", "roof_class": "pitched"} for i in range(30)] + [{"id": f"f{i}", "roof_class": "flat"} for i in range(5)]
            + [{"id": f"c{i}", "roof_class": "pitched", "complexity": "complex"} for i in range(5)])
    got = blind.stratified_draw(rows, 9, seed=3)
    strata = [data.pooled_stratum(r) for r in got]
    assert len(got) == 9 and all(strata.count(s) == 3 for s in ("pitched", "flat+mixed", "complex"))
    assert blind.stratified_draw(rows, 9, seed=3) == got and blind.stratified_draw(rows, 9, seed=4) != got


def test_blind_score_counts_wilson_and_agreement(tmp_path):
    key = {"houses": {f"H{i:03d}": {"id": f"h{i}", "stratum": "pitched" if i < 6 else "complex", "X": "lib", "Y": "new", "Z": "alt"}
                      for i in range(1, 11)}}
    lines = ["house\tgrader\tX\tY\tZ"]
    for i in range(1, 11):
        lines.append(f"H{i:03d}\tg1\t{'A' if i <= 5 else 'C'}\tA\tB")
        lines.append(f"H{i:03d}\tg2\t{'A' if i <= 4 else 'B'}\tA\tB")
    f = tmp_path / "grades.tsv"
    f.write_text("\n".join(lines) + "\n")
    res = blind_score.score(blind_score.read_grades(f), key)
    lib = res["candidates"]["lib"]["overall"]
    assert (lib["A"], lib["B"], lib["C"], lib["n"]) == (9, 6, 5, 20)
    assert lib["A_share"]["share"] == pytest.approx(0.45) and lib["A_share"]["lo95"] < 0.45 < lib["A_share"]["hi95"]
    assert res["candidates"]["new"]["overall"]["A_share"]["k"] == 20
    assert res["candidates"]["lib"]["stratum:complex"]["n"] == 10
    assert res["agreement"]["g1~g2"]["same"] == 24 and res["agreement"]["g1~g2"]["cells"] == 30
    only = blind_score.score(blind_score.read_grades(f), key, ["g2"])
    assert only["candidates"]["lib"]["overall"]["n"] == 10
    long = tmp_path / "long.tsv"
    long.write_text("H001\tg1\tX\tA\nH001\tg1\tY\tB\n")
    assert blind_score.read_grades(long) == [("H001", "g1", "X", "A"), ("H001", "g1", "Y", "B")]
    bad = tmp_path / "bad.tsv"
    bad.write_text("H001\tg1\tX\tQ\n")
    with pytest.raises(SystemExit, match="bad grade"):
        blind_score.read_grades(bad)
    assert "A share" in blind_score.render(res)


def test_gate_min_n_counts_houses_with_a_value():
    recs = [{"id": f"h{i}", "row": {"tiers": ["T2"] if i < 2 else []}, "automation_ok": True,
             "truth": {"T2": {"facet_iou.mean_iou": 0.9}} if i < 2 else {}} for i in range(12)]
    g = {"name": "shape", "metric": "truth.T2.facet_iou.mean_iou", "agg": "mean", "op": ">=", "value": 0.6, "min_n": 10}
    r = gates.evaluate({"gates": [g]}, recs)[0]
    assert not r["passed"] and r["n"] == 12 and r["n_value"] == 2 and "insufficient" in r["note"]
    assert gates.evaluate({"gates": [{**g, "min_n": 2}]}, recs)[0]["passed"]
    r = gates.evaluate({"gates": [{**g, "where": ["tiers=T2"]}]}, recs)[0]
    assert r["n"] == 2 and r["n_value"] == 2
    assert gates.evaluate({"gates": [{**g, "agg": "rate", "metric": "automation_ok", "min_n": 10}]}, recs)[0]["passed"]
    spec = json.loads((Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "gates" / "tuning.json").read_text())
    t2 = next(x for x in spec["gates"] if x["name"].startswith("6 T2"))
    assert t2["where"] == ["tiers=T2"]


def test_blind_score_two_candidates_wide_and_long_and_loud_errors(tmp_path):
    key = {"houses": {"H001": {"id": "a", "stratum": "pitched", "X": "lib", "Y": "new", "ok": {"X": True, "Y": False}},
                      "H002": {"id": "b", "stratum": "pitched", "X": "new", "Y": "lib", "ok": {"X": False, "Y": True}}}}
    wide = tmp_path / "w.tsv"
    wide.write_text("house\tgrader\tX\tY\nH001\tg1\tA\tB\nH002\tg1\tC\tA\n")
    assert blind_score.read_grades(wide) == [("H001", "g1", "X", "A"), ("H001", "g1", "Y", "B"), ("H002", "g1", "X", "C"), ("H002", "g1", "Y", "A")]
    nohead = tmp_path / "n.tsv"
    nohead.write_text("H001\tg1\tA\tB\n")
    assert blind_score.read_grades(nohead) == [("H001", "g1", "X", "A"), ("H001", "g1", "Y", "B")]  # two grades, not (letter A, grade B)
    res = blind_score.score(blind_score.read_grades(wide), key)
    assert res["candidates"]["lib"]["overall"]["n"] == 2 and res["candidates"]["new"]["overall"]["n"] == 2 and not res["unknown_houses"]
    assert res["candidates"]["lib"]["labelled_ok"]["n"] == 2 and "labelled_ok" not in res["candidates"]["new"]
    long = tmp_path / "l.tsv"
    long.write_text("house\tgrader\tcandidate\tgrade\nH001\tg1\tY\tC\n")
    assert blind_score.read_grades(long) == [("H001", "g1", "Y", "C")]
    bad = tmp_path / "b.tsv"
    bad.write_text("house\tgrader\tX\tQ\nH001\tg1\tA\tB\n")
    with pytest.raises(SystemExit, match="unknown candidate letter"):
        blind_score.read_grades(bad)
    third = tmp_path / "t.tsv"
    third.write_text("H001\tg1\tX\tA\nH001\tg1\tZ\tA\n")
    with pytest.raises(SystemExit, match="no such candidate"):
        blind_score.score(blind_score.read_grades(third), key)
    assert "independent" in blind_score.render(res)


def test_digest_ignores_runtimes_and_stderr(root, tmp_path):
    runner.evaluate(cfg_for(root, tmp_path, "perfect"))
    recs = [json.loads(ln) for ln in (tmp_path / "run" / "per_house.jsonl").read_text().splitlines()]
    d = runner.digest(recs)
    for r in recs:
        r["runtime_s"] += 5.0
        r["engine"]["stderr_tail"] = "different"
    assert runner.digest(recs) == d


def test_summary_reports_priced_inconsistency_and_drawn_t3(root, tmp_path):
    s = runner.evaluate(cfg_for(root, tmp_path, "perfect"))
    assert s["overall"]["priced_inconsistent_houses"] == 0 and s["overall"]["priced_from_totals_houses"] == 0
    assert s["t3"]["median_ratio"] == pytest.approx(s["t3_drawn"]["median_ratio"])  # no priced totals: both are the drawn value
    assert "priced totals read from the engine" in (tmp_path / "run" / "tables.md").read_text()
