"""The ``flat_seam`` edge type (library 0.5.1) is drawn, never priced and never counted by the harness: it must not enter
lengths, the false level-change share or the cleanliness edge counts."""

import copy

import numpy as np
import pytest
import roof_eval_helpers as H
from shapely.geometry import Polygon

from tools.roof_eval import m_fit, m_shape, score, seam_check
from tools.roof_eval.geom import EDGE_TYPES, UNCOUNTED_EDGE_TYPES, load_roof

REF = H.gable_points()
FOOT = Polygon(H.footprint())


def with_seam(res, ft=40.0):
    """A flat_seam edge across the roof (a long one, and a short one that would be a < 3 ft edge)."""
    r = copy.deepcopy(res)
    r["edges"].append(H.edge("flat_seam", (3.0, 1.0, 3.5), (3.0 + ft * 0.3048, 1.0, 3.5), ["f1"]))
    r["edges"].append(H.edge("flat_seam", (1.0, 1.0, 3.5), (1.5, 1.0, 3.5), ["f1"]))
    return r


def test_flat_seam_is_a_known_type_not_unspecified():
    assert "flat_seam" in EDGE_TYPES and UNCOUNTED_EDGE_TYPES == ("flat_seam",)
    roof = load_roof(with_seam(H.gable_result()))
    assert sum(e.type == "flat_seam" for e in roof.edges) == 2 and not any(e.type == "unspecified" for e in roof.edges)


def test_counted_edges_lengths_and_cleanliness_ignore_it():
    plain = load_roof(H.gable_result())
    seamed = load_roof(with_seam(H.gable_result()))
    assert len(seamed.edges) == len(plain.edges) + 2 and len(seamed.counted_edges) == len(plain.edges)
    assert m_shape.lengths(seamed) == m_shape.lengths(plain)
    assert m_shape.cleanliness(seamed, FOOT) == m_shape.cleanliness(plain, FOOT)  # edge count, < 3 ft, axis shares unchanged


def test_false_level_change_share_is_not_diluted_by_a_flat_seam():
    res = H.with_level_change(H.gable_result())  # one level_change across a continuous surface: false
    base = m_fit.false_level_change(load_roof(res), REF)
    seamed = m_fit.false_level_change(load_roof(with_seam(res, ft=500.0)), REF)
    assert base["count"] == 1 and base["share"] > 0
    assert seamed["share"] == pytest.approx(base["share"]) and seamed["false_ft"] == pytest.approx(base["false_ft"])
    assert seamed["edges"] == base["edges"] == 1


def test_full_score_is_identical_with_and_without_the_seam():
    a = score.score_house(H.gable_result(), REF, FOOT, [])["m"]
    b = score.score_house(with_seam(H.gable_result()), REF, FOOT, [])["m"]
    for k in ("lengths", "edges", "edges_lt_3ft", "edges_lt_3ft_share", "false_level_change_share", "false_unmarked_ft",
              "edge_len_ft", "perimeter_ft", "offaxis_controllable_share", "axis_share_7deg"):
        assert a[k] == b[k], k


# ---- gate 3l checks flat/flat seams from strip medians of the raw returns, independent of the engine ----
def two_decks(plane_b, a_plane=(0.0, 0.0, 3.0), engine_edge=None):
    res = H.gable_result()
    res["facets"] = [H.facet("a", H.rect(0, 0, 6, 8), a_plane), H.facet("b", H.rect(6, 0, 12, 8), plane_b)]
    res["edges"] = [H.edge(engine_edge, (6, 0.5, 3.0), (6, 7.5, 3.0), ["a", "b"])] if engine_edge else []
    return res


def deck_points(z_of_x, noise=0.0, step=0.25):
    xs, ys = np.arange(step, H.W, step), np.arange(step, H.D, step)
    X, Y = np.meshgrid(xs, ys)
    Z = z_of_x(X)
    if noise:
        Z = Z + np.random.default_rng(3).normal(0, noise, Z.shape)
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)


def seam_types(res, pts):
    from tools.roof_eval import edges_re

    rc = edges_re.recompute(load_roof(res), pts)
    return [e.type for e in rc.edges if set(e.facets) == {"a", "b"}]


def metrics_of(res, pts):
    return score.score_house(res, pts, FOOT, [])["m"]


def test_strip_step_unit_cases():
    from shapely.geometry import box

    pts = deck_points(lambda x: np.where(x < 6, 3.0, 5.0))
    a, b = box(0, 0, 6, 8), box(6, 0, 12, 8)
    assert seam_check.strip_step(pts, a, b, (6, 0), (6, 8)) is True
    flat = deck_points(lambda x: 3.0 + 0 * x)
    assert seam_check.strip_step(flat, a, b, (6, 0), (6, 8)) is False
    assert seam_check.strip_step(pts, a, b, (6, 0), (6, 0.8)) is None  # shorter than 1 m
    assert seam_check.strip_step(pts[:0], a, b, (6, 0), (6, 8)) is None
    sparse = pts[::40]  # a few returns only: fewer than 4 per strip
    assert seam_check.strip_step(sparse, a, b, (6, 0), (6, 8)) is None


def test_gently_sloped_deck_cut_into_pieces_is_not_a_step():
    res = two_decks((0.05, 0.0, 2.7), a_plane=(0.05, 0.0, 2.7))  # one continuous deck falling 0.6/12, cut at x = 6
    pts = deck_points(lambda x: 2.7 + 0.05 * x)
    assert "level_change" not in seam_types(res, pts)
    assert metrics_of(res, pts)["false_unmarked_ft"] == 0
    res = two_decks((0.05, 0.0, 2.7), a_plane=(0.05, 0.0, 2.7), engine_edge="flat_seam")
    assert metrics_of(res, pts)["false_unmarked_ft"] == 0  # the engine's flat_seam agrees


def test_a_3_5_m_step_with_noisy_edge_returns_marked_flat_seam_is_unmarked():
    rng = np.random.default_rng(5)
    pts = deck_points(lambda x: np.where(x < 6, 3.0, 6.5), noise=0.03)
    seam = np.c_[6 + rng.uniform(-0.3, 0.3, 300), rng.uniform(0, 8, 300), rng.uniform(3.0, 6.5, 300)]  # returns on the wall
    pts = np.vstack([pts, seam])
    wrong = two_decks((0.0, 0.0, 6.5), engine_edge="flat_seam")
    assert "level_change" in seam_types(wrong, pts)
    assert metrics_of(wrong, pts)["false_unmarked_ft"] == pytest.approx(8 / 0.3048, rel=0.1)
    right = two_decks((0.0, 0.0, 6.5), engine_edge="level_change")
    assert metrics_of(right, pts)["false_unmarked_ft"] == 0


def test_a_constant_two_metre_step_the_engine_did_not_mark_is_still_counted():
    res = two_decks((0.0, 0.0, 5.0))
    pts = deck_points(lambda x: np.where(x < 6, 3.0, 5.0))
    assert "level_change" in seam_types(res, pts)
    assert metrics_of(res, pts)["false_unmarked_ft"] == pytest.approx(8 / 0.3048, rel=0.05)


def test_an_engine_level_change_on_a_continuous_deck_is_false():
    res = two_decks((0.0, 0.0, 3.0), engine_edge="level_change")
    pts = deck_points(lambda x: 3.0 + 0 * x)
    m = metrics_of(res, pts)
    assert m["false_level_change_count"] == 1 and m["false_level_change_share"] > 0
    real = two_decks((0.0, 0.0, 5.0), engine_edge="level_change")
    m = metrics_of(real, deck_points(lambda x: np.where(x < 6, 3.0, 5.0)))
    assert m["false_level_change_count"] == 0 and m["false_unmarked_ft"] == 0


def test_a_seam_with_too_few_returns_is_not_evaluable_and_counts_in_no_numerator():
    res = two_decks((0.0, 0.0, 5.0), engine_edge="level_change")
    pts = deck_points(lambda x: np.where(x < 6, 3.0, 5.0), step=2.0)  # a few returns per strip
    assert "level_change" not in seam_types(res, pts)
    m = metrics_of(res, pts)
    assert m["false_level_change_count"] == 0 and m["level_change_unverified"] == 1 and m["false_unmarked_ft"] == 0
