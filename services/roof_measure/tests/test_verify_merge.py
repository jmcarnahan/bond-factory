"""Deterministic collinear merge: edge cases, self-consistency, determinism."""

import copy
import json
from pathlib import Path

from roof_measure.model import validate
from roof_measure.verify_merge import _chains, merge_collinear, turning_deg

FIX = Path(__file__).resolve().parents[3] / "fixtures"


def hip() -> dict:
    return json.loads((FIX / "synthetic_hip.json").read_text())


def split_edge(model: dict, edge_id: str, pts: list[list[float]]) -> dict:
    """Replace one 2-point edge by a chain through ``pts`` (interior points), keeping facet polygons in step."""
    m = copy.deepcopy(model)
    e = next(x for x in m["edges"] if x["id"] == edge_id)
    a, b = e["points"]
    chain = [a, *pts, b]
    new = []
    for i in range(len(chain) - 1):
        d = ((chain[i + 1][0] - chain[i][0]) ** 2 + (chain[i + 1][1] - chain[i][1]) ** 2) ** 0.5
        new.append({"id": e["id"] if i == 0 else f"{e['id']}_{i}", "type": e["type"],
                    "points": [chain[i], chain[i + 1]], "length_ft": d, "facets": list(e["facets"])})
    m["edges"] = [x for x in m["edges"] if x["id"] != edge_id] + new
    for f in m["facets"]:
        if f["id"] not in e["facets"]:
            continue
        poly = f["polygon"]
        for i in range(len(poly)):
            if poly[i] == a and poly[(i + 1) % len(poly)] == b:
                f["polygon"] = poly[:i + 1] + pts + poly[i + 1:]
                break
    m["totals"]["lengths_ft"][e["type"]] = sum(x["length_ft"] for x in m["edges"] if x["type"] == e["type"])
    return m


STRAIGHT = [[14.0, 0.0], [15.5, 0.0], [17.0, 0.0], [18.5, 0.0]]  # 35 ft eave e1 as 14 + 1.5 x3 + 16.5


def test_straight_chain_of_five_becomes_one_edge():
    m = split_edge(hip(), "e1", STRAIGHT)
    assert len(m["edges"]) == 13
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert len(out["edges"]) == 9 and len(adj) == 1
    e1 = next(e for e in out["edges"] if e["id"] == "e1")
    assert e1["points"] == [[0.0, 0.0], [35.0, 0.0]] and abs(e1["length_ft"] - 35.0) < 1e-6
    assert adj[0]["edge_ids"] == ["e1", "e1_1", "e1_2", "e1_3", "e1_4"] and adj[0]["edge_type"] == "eave"
    assert adj[0]["op"] == "merge_collinear" and adj[0]["length_after_ft"] == 35.0
    assert len(next(f for f in out["facets"] if f["id"] == "f1")["polygon"]) == 4
    assert abs(out["totals"]["lengths_ft"]["eave"] - 122.0) < 1e-4
    validate(out)


def test_zigzag_moves_totals_slightly_and_stays_valid():
    m = split_edge(hip(), "e1", [[14.0, 0.0], [15.5, 0.06], [17.0, 0.0], [18.5, 0.04]])
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert adj and all(a["length_after_ft"] <= a["length_before_ft"] for a in adj)
    validate(out)


def test_kink_of_ten_degrees_is_not_merged():
    m = split_edge(hip(), "e1", [[17.0, 0.0], [17.0 + 1.5, 0.265]])  # 10 deg turn at the second vertex
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert adj == [] and len(out["edges"]) == len(m["edges"])  # 10 and 10.9 degree turns: nothing merges


def test_two_point_degenerate_chain_merges():
    m = split_edge(hip(), "e1", [[17.0, 0.0]])
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert len(adj) == 1 and len(adj[0]["edge_ids"]) == 2
    assert len(out["edges"]) == 9


def test_interior_segment_longer_than_min_len_blocks_a_three_chain():
    m = split_edge(hip(), "e1", [[10.0, 0.0], [20.0, 0.0]])  # middle piece 10 ft
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert len(adj) == 1 and len(adj[0]["edge_ids"]) == 2  # only the first 10 ft pair: no 3-chain
    assert len(out["edges"]) == len(m["edges"]) - 1


def test_never_merges_across_facet_sets_or_types():
    m = split_edge(hip(), "e1", [[17.0, 0.0]])
    m["edges"][-1]["facets"] = ["f2"]  # second half now belongs to another facet
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert adj == [] and len(out["edges"]) == len(m["edges"])
    m = split_edge(hip(), "e1", [[17.0, 0.0]])
    m["edges"][-1]["type"] = "rake"
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert adj == []


def test_input_not_mutated_and_two_runs_byte_identical():
    m = split_edge(hip(), "e1", STRAIGHT)
    before = json.dumps(m, sort_keys=True)
    a, adj_a = merge_collinear(m, 3.0, 2.0)
    b, adj_b = merge_collinear(m, 3.0, 2.0)
    assert json.dumps(m, sort_keys=True) == before
    assert json.dumps([a, adj_a], sort_keys=True) == json.dumps([b, adj_b], sort_keys=True)


def test_clean_model_is_returned_unchanged():
    m = hip()
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert adj == [] and out == m and out is not m


def stretch(model: dict, sx: float) -> dict:
    """Scale x by ``sx`` everywhere (edges keep the slope ratio of hips and valleys)."""
    m = copy.deepcopy(model)
    sc = lambda p: [p[0] * sx, p[1]]
    for b in m["blocks"]:
        b["polygon"] = [sc(p) for p in b["polygon"]]
    for f in m["facets"]:
        f["polygon"] = [sc(p) for p in f["polygon"]]
    for e in m["edges"]:
        e["points"] = [sc(p) for p in e["points"]]
        e["length_ft"] = ((e["points"][1][0] - e["points"][0][0]) ** 2 + (e["points"][1][1] - e["points"][0][1]) ** 2) ** 0.5 \
            * (1.0274022 if e["type"] in ("hip", "valley") else 1.0)
    return m


def test_chord_deviation_cap_blocks_a_long_bulge():
    m = split_edge(stretch(hip(), 3.0), "e1", [[51.5, 2.61], [53.5, 2.61]])  # 2.9 deg turns, 2.6 ft off the chord
    out, adj = merge_collinear(m, 3.0, 2.0)
    assert all(len(a["edge_ids"]) == 2 for a in adj)  # the 3-chain that swallows both bulge vertices is refused
    assert len(out["edges"]) >= len(m["edges"]) - 1


def test_one_bad_chain_does_not_discard_the_good_one():
    m = split_edge(hip(), "e1", [[17.0, 0.0]])
    m = split_edge(m, "e2", [[35.0, 13.0]])

    def check(model):  # refuses the e1 chain only (its facet loses the vertex)
        if len(next(f for f in model["facets"] if f["id"] == "f1")["polygon"]) < 5:
            raise ValueError("no")

    out, adj = merge_collinear(m, 3.0, 2.0, check)
    assert [a["edge_ids"][0] for a in adj] == ["e2"] and len(out["edges"]) == 10


def test_exact_tolerance_is_not_lost_to_float_noise():
    a, b = [0.0, 0.0], [5.0, 0.0]
    import math
    c = [b[0] + 10 * math.cos(math.radians(3.0)), 10 * math.sin(math.radians(3.0))]
    assert abs(turning_deg((1.0, 0.0), (c[0] - b[0], c[1] - b[1])) - 3.0) < 1e-9  # exactly the tolerance
    e1 = {"id": "a", "length_ft": 5.0}
    e2 = {"id": "b", "length_ft": 10.0}
    chains = _chains([(e1, a, b), (e2, b, c)], 3.0, 2.0)
    assert len(chains) == 1 and len(chains[0]) == 2
