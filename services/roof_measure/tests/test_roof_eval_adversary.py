"""Hardening against degenerate and malicious engines (adversary findings): sanitised input, over-segmentation, padding,
recomputed edges, malformed output, loud missing gates, the real gate files. Synthetic data only."""

import json
import shlex
import sys
from pathlib import Path

import pytest
import roof_eval_helpers as H
from shapely.geometry import Polygon

from tools.roof_eval import blind_score, cli, data, edges_re, gates, runner, score, validate
from tools.roof_eval.geom import load_roof

STUB = str(Path(__file__).with_name("roof_eval_stub_engine.py"))
GATES = Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "gates"
REF = H.gable_points()
FOOT = Polygon(H.footprint())


def engine(mode):
    return f"{shlex.quote(sys.executable)} {shlex.quote(STUB)} {mode} {{house_dir}} {{out_json}}"


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "data"
    H.build_root(r, n=4)
    return r


def run(root, tmp_path, mode, name=None, **kw):
    cfg = runner.Config(root=root, out_dir=tmp_path / (name or mode), engine=engine(mode), split="all", jobs=2, **kw)
    s = runner.evaluate(cfg)
    recs = [json.loads(ln) for ln in (cfg.out_dir / "per_house.jsonl").read_text().splitlines()]
    return s, recs


def sc(res, ref=REF, facet_ref=None):
    return score.score_house(res, ref, FOOT, [], None, facet_ref)


# ---- (1) sanitised engine input ----
def test_engine_sees_only_sanitised_inputs(root, tmp_path):
    (root / "houses" / "h-00000000" / "reference_points.npy").exists() or data.reference_points(root / "houses" / "h-00000000")
    (root / "houses" / "h-00000000" / "envelope.json").write_text("{}")
    run(root, tmp_path, "listing")
    d = json.loads((tmp_path / "listing" / "results" / "h-00000000.json").read_text())["diagnostics"]
    assert d["listing"] == ["footprint.json", "meta.json", "points.npy", "points_wide.npy"]
    assert set(d["meta"]) <= {"frame", "outline_source", "parcel_match"} and d["meta"]["parcel_match"] == "exact"
    assert "density" not in d["meta"]
    assert d["parent"] == ["h-00000000"]  # no sibling houses, truth or baselines next to it


def test_engine_reading_reference_points_fails(root, tmp_path):
    for hid in ("h-00000000", "h-00000001", "h-00000002", "h-00000003"):
        data.reference_points(root / "houses" / hid)
        (root / "houses" / hid / "envelope.json").write_text("{}")
    s, recs = run(root, tmp_path, "peek")
    assert s["overall"]["failures"] == {"failed": 4} and all(r["invalid_or_crashed"] == 1 for r in recs)


# ---- (2) over-segmentation, (3) precision ----
def test_split_in_two_and_cells_fail_mergeable_and_count_ratio(root, tmp_path):
    _, good = run(root, tmp_path, "perfect")
    for mode in ("split2", "cells"):
        _, bad = run(root, tmp_path, mode)
        for r, g in zip(bad, good, strict=True):
            assert r["m"]["mergeable_neighbour_share"] >= 0.5 and g["m"]["mergeable_neighbour_share"] == 0, mode
            assert r["m"]["facet_count_ratio"] >= 2.0 > g["m"]["facet_count_ratio"] == 1.0, mode
            assert r["m"]["fit_all"] > 0.95  # planes are right: only the new metrics catch it
    assert good[0]["m"]["facets_per_1000sqft"] < 2.5


def test_tuning_gates_catch_over_segmentation(root, tmp_path):
    spec = json.loads((GATES / "tuning.json").read_text())
    for g in spec["gates"]:
        g.pop("min_n", None)
        g.pop("where", None) if g["name"].startswith("1 ") else None
    names = ("3h", "3i", "3j")
    _, recs = run(root, tmp_path, "split2")
    bad = {g["name"][:2]: g for g in gates.evaluate(spec, recs)}
    assert not bad["3i"]["passed"] and not bad["3j"]["passed"]  # half of the neighbour pairs are coplanar
    _, recs = run(root, tmp_path, "cells")
    bad = {g["name"][:2]: g for g in gates.evaluate(spec, recs)}
    assert not bad["3h"]["passed"] and not bad["3i"]["passed"] and not bad["3g"]["passed"]
    _, recs = run(root, tmp_path, "perfect")
    ok = {g["name"][:2]: g for g in gates.evaluate(spec, recs)}
    assert all(ok[n]["passed"] for n in names + ("3k", "3l", "2e", "2f"))


def test_padded_facet_is_unsupported_and_outside_the_outline(root, tmp_path):
    _, recs = run(root, tmp_path, "onefacet_big")
    m = recs[0]["m"]
    assert m["unsupported_facet_area_share"] > 0.4 and m["outside_outline_area_share"] > 0.2
    assert sc(H.gable_result())["m"]["unsupported_facet_area_share"] == 0
    assert sc(H.gable_result())["m"]["outside_outline_area_share"] == 0


def test_shrunken_roof_has_no_unsupported_area(root):
    assert sc(H.shrunk(H.gable_result(), 1.5))["m"]["unsupported_facet_area_share"] == 0  # precision is not recall


# ---- (4) edges recomputed, not trusted ----
def test_unmarked_level_change_counts_and_unverifiable_is_separate():
    pts = H.two_level_points(1.0)
    res = {"facets": [H.facet("l", H.rect(0, 0, 6, H.D), (0, 0, 3.0)), H.facet("r", H.rect(6, 0, H.W, H.D), (0, 0, 4.0))],
           "edges": [], "roof_outline": H.rect(0, 0, H.W, H.D)}
    m = sc(res, pts)["m"]
    assert m["level_change_ft"] == pytest.approx(8 / 0.3048, rel=0.02) and m["unmarked_level_change_ft"] == pytest.approx(m["level_change_ft"])
    assert m["false_unmarked_ft"] > 20 and m["level_change_unverified_ft"] == 0
    res["edges"] = [H.edge("level_change", (6, 0, 3), (6, 8, 3), ["l", "r"])]
    m = sc(res, pts)["m"]
    assert m["unmarked_level_change_ft"] == 0 and m["false_unmarked_ft"] == 0
    # no points beside the edge: a plane gap >= 0.3 m is reported separately and is not a verified level change
    m = sc({**res, "edges": []}, REF[:0])["m"]
    assert m["level_change_ft"] == 0 and m["level_change_unverified_ft"] > 20 and m["unmarked_level_change_ft"] == 0


def test_edge_lengths_come_from_the_facets_not_the_engine_list():
    res = H.gable_result()
    lie = {**res, "edges": [H.edge("ridge", (0, 0, 3), (500, 0, 3), ["f1"]), H.edge("level_change", (0, 0, 3), (300, 0, 3), ["f1"])]}
    m = sc(lie)["m"]
    assert m["lengths"]["ridge"] == pytest.approx(12 / 0.3048, rel=1e-3) and m["level_change_ft"] == 0
    assert m["edge_list_disagreement_ft"] > 1000
    honest = sc(res)["m"]
    assert honest["edge_list_disagreement_ft"] < 0.5  # an honest list agrees with the recomputed one


def test_recomputed_edge_types_by_geometry():
    roof = load_roof(H.gable_result())
    rc = edges_re.recompute(roof, REF)
    by = {}
    for e in rc.edges:
        by[e.type] = by.get(e.type, 0) + e.length_ft
    assert sorted(by) == ["eave", "rake", "ridge"] and by["ridge"] == pytest.approx(12 / 0.3048, rel=1e-3)
    valley = {"facets": [H.facet("a", H.rect(0, 0, 4, 4), (0.5, 0, 3.0)), H.facet("b", H.rect(4, 0, 8, 4), (-0.5, 0, 7.0))]}
    types = {e.type for e in edges_re.recompute(load_roof(valley), REF[:0]).edges}
    assert "ridge" in types
    valley["facets"][0]["plane"] = (-0.5, 0, 3.0)
    valley["facets"][1]["plane"] = (0.5, 0, -1.0)
    assert "valley" in {e.type for e in edges_re.recompute(load_roof(valley), REF[:0]).edges}


# ---- (5) fail loudly ----
@pytest.mark.parametrize("mode", ["badjson", "list", "empty_obj", "nan_plane", "inf_plane", "no_plane", "str_facets", "facets_not_list",
                                  "verdict_list", "nan_poly", "huge"])
def test_malformed_results_are_invalid_not_refused(root, tmp_path, mode):
    _, recs = run(root, tmp_path, mode)
    assert {r["status"] for r in recs} == {"invalid"} and all(r["invalid_or_crashed"] == 1 and r["invalid_reasons"] for r in recs)
    spec = {"gates": [{"name": "invalid or crashed = 0", "metric": "invalid_or_crashed", "agg": "sum", "op": "==", "value": 0}]}
    assert not gates.evaluate(spec, recs)[0]["passed"]


def test_refused_is_valid_and_crashed_counts_as_invalid_or_crashed(root, tmp_path):
    _, recs = run(root, tmp_path, "refuse")
    assert {r["status"] for r in recs} == {"empty"} and all(r["invalid_or_crashed"] == 0 for r in recs)
    _, recs = run(root, tmp_path, "crash")
    assert {r["status"] for r in recs} == {"no_result"} and all(r["invalid_or_crashed"] == 1 for r in recs)


def test_validate_accepts_a_good_result_and_names_problems():
    assert validate.problems(H.gable_result()) == []
    assert validate.problems({"facets": []}) == []
    assert validate.problems({"facets": [{"polygon": H.rect(0, 0, 1, 1)}]}) == ["facet 0: missing or non-finite plane"]
    assert validate.problems([]) and validate.problems({"edges": []})


def test_no_gates_exits_3_unless_asked(root, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROOF_EVAL_OUT", str(tmp_path / "out"))
    base = ["eval", "--data", str(root), "--split", "all", "--engine", engine("perfect"), "--jobs", "2"]
    assert cli.main(base) == 3
    assert "NO GATES EVALUATED" in capsys.readouterr().err
    assert cli.main([*base, "--no-gates"]) == 0
    assert "NO GATES EVALUATED" in capsys.readouterr().out
    assert cli.main(["eval", *base[1:5], "--split", "tuning", "--engine", engine("perfect"), "--jobs", "2"]) == 1  # tuning.json found; 3 houses fail min_n


# ---- (6) the real gate files ----
def test_gate_files_encode_the_plan_and_heldout_differs_only_in_on_insufficient():
    tuning = json.loads((GATES / "tuning.json").read_text())
    held = json.loads((GATES / "heldout.json").read_text())
    assert len(tuning["gates"]) == 23 and not (GATES.parent / "gates.example.json").exists()
    strip = lambda spec: [{k: v for k, v in g.items() if k != "on_insufficient"} for g in spec["gates"]]
    assert strip(tuning) == strip(held) and tuning["compare"] == held["compare"]
    assert [g.get("on_insufficient") for g in tuning["gates"] if "on_insufficient" in g] == []  # too few houses fails everywhere
    assert [g.get("on_insufficient") for g in held["gates"] if "on_insufficient" in g] == ["fail"]
    byname = {g["name"][:2]: g for g in tuning["gates"]}
    assert byname["1 "]["value"] == 0.90 and byname["1 "]["where"] == ["parcel_match=exact", "density_pts_m2>=6", "flags!=derived_thin"]
    assert (byname["2a"]["pred"]["value"], byname["2a"]["value"]) == (0.80, 0.60)
    assert (byname["3g"]["value"], byname["3l"]["value"], byname["3d"]["value"]) == (5.5, 0.025, 0.27)
    assert byname["7b"]["value"] == 1.35 and byname["7b"]["baseline"] == "library-0.4.0"
    synth = json.loads((GATES / "synth.json").read_text())["synth_gates"]
    assert (synth["area_pct"], synth["length_pct"], synth["length_floor_ft"]) == (2.0, 5.0, 1.0)


def test_negative_gate_file_passes_refusal_and_fails_an_ok_label(root, tmp_path):
    spec = json.loads((GATES / "negative.json").read_text())
    _, recs = run(root, tmp_path, "refuse")
    neg = [r for r in recs if r["row"]["split"] == "negative"]
    assert all(g["passed"] for g in gates.evaluate(spec, neg))  # a refuse-everything engine needs no automation gate
    _, recs = run(root, tmp_path, "perfect")
    assert not all(g["passed"] for g in gates.evaluate(spec, [r for r in recs if r["row"]["split"] == "negative"]))


def test_numeric_where_and_t3_gates():
    rows = [{"id": f"h{i}", "row": {"density_pts_m2": 4.0 + 2 * i, "flags": ["derived_thin"] if i == 3 else []}, "automation_ok": True,
             "truth_files": [{"tier": "T3", "confidence": "medium", "squares": {"ratio": 0.9 + 0.05 * i}}]} for i in range(5)]
    g = {"name": "auto", "metric": "automation_ok", "agg": "rate", "op": ">=", "value": 1.0, "where": ["density_pts_m2>=6", "flags!=derived_thin"]}
    assert gates.evaluate({"gates": [g]}, rows)[0]["n"] == 3  # 6, 8, 12 (the 10 is thinned; 4 is below 6)
    t = gates.evaluate({"gates": [{"name": "t3", "agg": "t3_contains", "op": ">=", "value": 1.0, "min_n": 3}]}, rows)[0]
    assert t["passed"] and t["n_value"] == 5
    base = {"base": {"iqr": 0.1}}
    q = {"name": "iqr", "agg": "t3_iqr_ratio", "baseline": "base", "op": "<=", "value": 1.35, "min_n": 3}
    r = gates.evaluate({"gates": [q]}, rows, lambda n: base[n])[0]
    assert r["value"] == pytest.approx(0.1 / 0.1) and r["passed"]
    assert not gates.evaluate({"gates": [{**q, "value": 0.5}]}, rows, lambda n: base[n])[0]["passed"]


# ---- stale references are refused, never silently scored ----
def test_stale_reference_refuses_to_score_and_rebuild_fixes_it(root, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROOF_EVAL_OUT", str(tmp_path / "out"))
    for hid in ("h-00000000", "h-00000001", "h-00000002", "h-00000003"):
        data.reference_points(root / "houses" / hid)
    side = root / "houses" / "h-00000001" / "reference_points.json"
    assert json.loads(side.read_text())["params_hash"] == data.REF_HASH and json.loads(side.read_text())["rule"] == data.REF_RULE
    base = ["eval", "--data", str(root), "--split", "all", "--engine", engine("perfect"), "--no-gates", "--jobs", "2"]
    assert cli.main(base) == 0
    side.write_text(json.dumps({"rule": data.REF_RULE, "params_hash": "deadbeef0000"}))  # a different rule
    assert data.reference_status(side.parent) == "stale"
    assert cli.main(base) == 2 and "refusing to score" in capsys.readouterr().err
    with pytest.raises(data.StaleReference, match="reference --rebuild"):
        data.reference_points(side.parent)
    (root / "houses" / "h-00000002" / "reference_points.json").unlink()  # no sidecar at all: also stale
    assert cli.main(["reference", "--data", str(root)]) == 1
    assert cli.main(["reference", "--data", str(root), "--rebuild"]) == 0
    assert cli.main(["reference", "--data", str(root)]) == 0 and cli.main(base) == 0


def test_rebuild_gives_derived_houses_their_parents_frozen_reference(root):
    parent, kid = root / "houses" / "h-00000000", root / "houses" / "h-00000000-t4"
    kid.mkdir()
    for f in ("points_wide.npy", "points.npy", "footprint.json"):
        (kid / f).write_bytes((parent / f).read_bytes())
    meta = {"derived_from": "h-00000000", "parcel_match": "exact"}
    (kid / "meta.json").write_text(json.dumps(meta))
    out = data.rebuild_references(root)
    assert out == {"derived": 4, "copied": 1, "orphans": 0}
    import numpy as np

    assert np.array_equal(np.load(kid / "reference_points.npy"), np.load(parent / "reference_points.npy"))
    assert json.loads((kid / "reference_points.json").read_text())["derived_from"] == "h-00000000"
    assert data.reference_status(kid) == "ok"


def test_reference_hash_covers_the_rule_parameters():
    import hashlib

    assert data.REF_HASH == hashlib.sha256(json.dumps(data.REF_PARAMS, sort_keys=True).encode()).hexdigest()[:12]
    assert data.REF_PARAMS["min_height_m"] == 1.5 and data.REF_PARAMS["footprint_buffer_m"] == 1.2


# ---- judge findings ----
def test_twice_with_failing_gates_exits_non_zero(root, tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_EVAL_OUT", str(tmp_path / "out"))
    gf = tmp_path / "g.json"
    gf.write_text(json.dumps({"gates": [{"name": "x", "metric": "fit_all", "agg": "median", "op": ">=", "value": 1.5}]}))
    base = ["eval", "--data", str(root), "--split", "all", "--engine", engine("perfect"), "--jobs", "2"]
    assert cli.main([*base, "--twice", "--gates", str(gf)]) == 1  # identical digests must not hide a failed gate
    gf.write_text(json.dumps({"gates": [{"name": "x", "metric": "fit_all", "agg": "median", "op": ">=", "value": 0.5}]}))
    assert cli.main([*base, "--twice", "--gates", str(gf)]) == 0
    assert cli.main([*base, "--gates", str(gf)]) == 0


def test_facet_count_gate_uses_only_independent_references():
    mk = lambda i, src, ratio: {"id": f"h{i}", "row": {"facet_count_src": src}, "automation_ok": True,
                                "m": {"facet_count_ratio": ratio}}
    recs = [mk(i, "library", 9.0) for i in range(30)] + [mk(100 + i, "vision_label", 1.0) for i in range(10)] + [mk(200, None, 7.0)]
    spec = json.loads((GATES / "tuning.json").read_text())
    g = next(x for x in spec["gates"] if x["name"].startswith("3h"))
    r = gates.evaluate({"gates": [g]}, recs)[0]
    assert r["n"] == 10 and r["passed"] and r["value"] == 1.0  # the 30 self-referential library references and the missing one are out
    assert not gates.evaluate({"gates": [g]}, recs[:35])[0]["passed"]  # < 10 independent references: insufficient
    held = next(x for x in json.loads((GATES / "heldout.json").read_text())["gates"] if x["name"].startswith("3h"))
    assert held["where"] == ["facet_count_src=vision_label,vendor,manual"]


def test_canaries_are_never_evidence_and_have_their_own_section(root, tmp_path):
    rows = json.loads((root / "manifest.json").read_text())
    rows[0]["canary"] = True
    rows[0]["split"] = "heldout"
    (root / "manifest.json").write_text(json.dumps(rows))
    cfg = runner.Config(root=root, out_dir=tmp_path / "c", engine=engine("refuse"), split="all", jobs=2)
    cfg.gates_file = tmp_path / "g.json"
    cfg.gates_file.write_text(json.dumps({"gates": [{"name": "n", "metric": "automation_ok", "agg": "count", "op": "==", "value": 3}]}))
    s = runner.evaluate(cfg)
    assert s["gates"][0]["passed"] and s["overall"]["n"] == 3  # 4 houses, 1 canary: the canary is not counted
    assert [c["id"] for c in s["canaries"]] == [rows[0]["id"]]
    assert "canaries (never counted as evidence)" in (tmp_path / "c" / "tables.md").read_text()


def test_blind_score_r_grades_and_note_columns(tmp_path):
    key = {"houses": {f"H{i}": {"id": f"h{i}", "stratum": "pitched", "X": "lib", "Y": "new", "ok": {"X": True, "Y": True}} for i in range(1, 7)}}
    f = tmp_path / "g.tsv"
    f.write_text("house\\tgrader\\tX\\tX_note\\tY\\tY_note\\n".replace("\\t", "\t").replace("\\n", "\n")
                 + "H1\tj\tA\tclean\tA\t\nH2\tj\tB\t\tR\tno drawing\nH3\tj\tC\tx\tA\t\nH4\tj\tA\t\tB\t\nH5\tj\tR\t\tC\t\nH6\tj\tB\t\tB\t\n")
    res = blind_score.score(blind_score.read_grades(f), key)
    x = res["candidates"]["lib"]["overall"]
    assert (x["A"], x["B"], x["C"], x["R"], x["n"], x["n_with_R"]) == (2, 2, 1, 1, 5, 6)  # R is outside the shares
    assert x["A_share"]["share"] == pytest.approx(2 / 5) and res["candidates"]["new"]["overall"]["R"] == 1
    assert "| R |" in blind_score.render(res)
    long = tmp_path / "l.tsv"
    long.write_text("H1\tj\tX\tR\tnote text\n")
    assert blind_score.read_grades(long) == [("H1", "j", "X", "R")]


def test_gate_7b_baseline_is_computed_on_the_fly_when_none_is_frozen(root, tmp_path, monkeypatch):
    for k in range(4):  # varied contractor squares so the IQR is not zero
        (root / "truth" / f"h-{k:08x}" / "truth.contractor_squares.json").write_text(json.dumps(
            {"source": "contractor_squares", "confidence": "medium", "squares": 8.0 + 2 * k}))
    spec = {"gates": [{"name": "7b", "agg": "t3_iqr_ratio", "baseline": "library-0.4.0", "op": "<=", "value": 1.35, "min_n": 3}]}
    gf = tmp_path / "g.json"
    gf.write_text(json.dumps(spec))
    calls = []
    monkeypatch.setattr(runner, "library_t3", lambda cfg, rows: calls.append(len(rows)) or {"n": 4, "iqr": 0.5})
    cfg = runner.Config(root=root, out_dir=tmp_path / "o", engine=engine("perfect"), split="all", jobs=2, gates_file=gf)
    s = runner.evaluate(cfg)
    assert calls == [4] and s["gates"][0]["value"] is not None
    # with a frozen baseline carrying an IQR nothing is recomputed
    (root / "baselines" / "library-0.4.0").mkdir(parents=True)
    (root / "baselines" / "library-0.4.0" / "metrics.json").write_text(json.dumps({"t3": {"iqr": 0.4}}))
    cfg.out_dir = tmp_path / "o2"
    runner.evaluate(cfg)
    assert calls == [4]


def test_library_t3_none_without_envelopes(root, tmp_path):
    cfg = runner.Config(root=root, out_dir=tmp_path / "o", engine=engine("perfect"), split="all", jobs=2)
    assert runner.library_t3(cfg, data.select_rows(data.load_manifest(root), "all")) is None


def test_price_rules_example_is_announced(root, tmp_path):
    ex = Path(__file__).resolve().parents[1] / "tools" / "roof_eval" / "price_rules.example.json"
    cfg = runner.Config(root=root, out_dir=tmp_path / "e", engine=engine("perfect"), split="all", jobs=2, price_rules=ex)
    s = runner.evaluate(cfg)
    assert s["price_rules"]["example"] is True and "EXAMPLE RULES" in (tmp_path / "e" / "tables.md").read_text()
    real = tmp_path / "rules.json"
    real.write_text(json.dumps({k: v for k, v in json.loads(ex.read_text()).items() if k != "_note"}))
    cfg2 = runner.Config(root=root, out_dir=tmp_path / "r", engine=engine("perfect"), split="all", jobs=2, price_rules=real)
    assert runner.evaluate(cfg2)["price_rules"]["example"] is False
    assert "EXAMPLE RULES" not in (tmp_path / "r" / "tables.md").read_text()


def test_t2_two_run_label_agreement_flag(root, tmp_path):
    from tools.roof_eval import m_shape

    a = H.truth_for(H.gable_result())
    same = [{**a, "tier": "T2"}, {**a, "tier": "T2", "source": "llm_vision"}]
    ag = m_shape.label_agreement(same)
    assert ag["iou"] == pytest.approx(1.0) and not ag["disagree"] and ag["n_files"] == 2
    other = {**a, "tier": "T2", "facets": [{"polygon": H.rect(0, 0, 4, 8), "pitch_rise": 6.0, "roof_type": "pitched"},
                                           {"polygon": H.rect(4, 0, 12, 8), "pitch_rise": 6.0, "roof_type": "pitched"}]}
    bad = m_shape.label_agreement([same[0], other])
    assert bad["disagree"] and bad["iou"] < 0.6
    assert m_shape.label_agreement([same[0]]) is None
    td = root / "truth" / "h-00000000"
    (td / "truth.llm_vision.json").write_text(json.dumps({**a, "source": "llm_vision", "confidence": "medium"}))
    (td / "truth.llm_vision_api.json").write_text(json.dumps({**other, "source": "llm_vision", "confidence": "medium"}))
    s = runner.evaluate(runner.Config(root=root, out_dir=tmp_path / "t", engine=engine("perfect"), split="all", jobs=2))
    assert s["overall"]["T2_two_label_houses"] == 1 and s["overall"]["T2_label_disagree"] == 1
