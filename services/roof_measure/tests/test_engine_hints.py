"""Engine hints (``library.measure(..., hints=)``): there are none today. ``{"steps": False}`` (a step line between two PITCHED
facets whose fitted planes agree at the seam is typed from the planes) is retired: the rule is the default now, so the answer
changed nothing. The typer tests below keep the rule itself; the library still validates what it is given. Synthetic data only."""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from test_engine_edges import CTX, facet, points_on
from test_pipeline_engine import no_network, run, world  # noqa: F401  (fixtures: the pipeline test's fakes)

from roof_measure import library
from roof_measure.engine import hints as H
from roof_measure.engine.edges import build_edges
from roof_measure.engine.params import DEFAULT

DEFAULT_HASH = "2d08a05e7fe5c0e9a75865d684e05cce0a5b1871638a6e92b6157fe893666d44"


def test_the_default_parameter_hash_is_pinned_and_there_is_no_hint_field():
    assert DEFAULT.stable_hash() == DEFAULT_HASH
    assert not hasattr(DEFAULT, "pitched_steps")


@pytest.mark.parametrize("hints", [None, {}])
def test_no_hint_is_the_default_parameters(hints):
    assert H.params_from_hints(hints) is DEFAULT and H.clean_hints(hints) is None


@pytest.mark.parametrize("hints,key", [({"nope": True}, "nope"), ({"steps": False}, "steps"), ({"steps": True}, "steps"),
                                       ({"x": 1}, "x")])
def test_every_key_is_unknown_and_named(hints, key):
    with pytest.raises(ValueError, match=key):
        H.params_from_hints(hints)
    with pytest.raises(ValueError, match=key):
        H.clean_hints(hints)


def test_a_hints_argument_that_is_not_a_dict_is_refused():
    with pytest.raises(ValueError, match="dict"):
        H.clean_hints([("steps", False)])


def test_library_measure_takes_hints_and_rejects_every_key(tmp_path):
    assert "hints" in inspect.signature(library.measure).parameters
    with pytest.raises(ValueError, match="steps"):
        library.measure("", lat=1.0, lng=2.0, cache_dir=tmp_path, engine="planes", hints={"steps": False})
    with pytest.raises(ValueError, match="bogus"):
        library.measure("", lat=1.0, lng=2.0, cache_dir=tmp_path, engine="planes", hints={"bogus": True})


# ---- the edge typer. Four 5 m wide facets in a row: a valley at x=5, a ridge at x=10, a valley at x=15, each 10 m long.
def _row(lift_b=0.5, lift_c=0.5, lift_b_plane=0.0):
    a = facet("A", [(0, 0), (5, 0), (5, 10), (0, 10)], (-0.5, 0, 5.5))
    b = facet("B", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0, 0.5 + lift_b_plane))
    c = facet("C", [(10, 0), (15, 0), (15, 10), (10, 10)], (-0.5, 0, 10.5))
    d = facet("D", [(15, 0), (20, 0), (20, 10), (15, 10)], (0.5, 0, -4.5))
    q = np.vstack([points_on(a, 800, 1), points_on(b, 800, 2, offset=lift_b), points_on(c, 800, 3, offset=lift_c),
                   points_on(d, 800, 4)])
    return [a, b, c, d], q


def _seams(facets, q, ctx=CTX):
    return {tuple(sorted(e.facets)): e for e in build_edges(facets, q, ctx) if len(e.facets) == 2}


# ---- the rule the hint became: a step between two pitched facets needs the planes apart too.
def test_a_point_jump_beside_agreeing_planes_is_typed_from_the_planes():
    facets, q = _row()  # B and C's points lie 0.5 m over their planes, which still meet A and D exactly
    seams = _seams(facets, q)
    assert seams[('A', 'B')].type == "valley" and seams[('C', 'D')].type == "valley" and seams[('B', 'C')].type == "ridge"
    assert seams[('A', 'B')].length_ft == pytest.approx(seams[('C', 'D')].length_ft, rel=0.05)
    assert all(e.jump_ft is None and e.upper is None for e in seams.values())


def test_the_same_when_the_points_agree_with_the_planes():
    facets, q = _row(lift_b=0.0, lift_c=0.0)
    assert {k: e.type for k, e in _seams(facets, q).items()} == {('A', 'B'): "valley", ('B', 'C'): "ridge", ('C', 'D'): "valley"}


def test_a_real_step_between_pitched_roofs_stays_a_step():
    low = facet("L", [(0, 0), (5, 0), (5, 10), (0, 10)], (-0.5, 0, 5.5))  # 3 m at the seam
    high = facet("H", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0, 1.0 + 0.5))  # 4 m at the seam: a 1 m wall
    q = np.vstack([points_on(low, 800, 1), points_on(high, 800, 2)])
    seam = _seams([low, high], q)[('H', 'L')]
    # L falls towards the seam and H stands over it: the lower roof drains into a higher wall, sidewall flashing
    assert seam.type == "step_flashing" and seam.upper == "H" and seam.jump_ft == pytest.approx(1.0 / 0.3048, abs=0.3)


def test_planes_that_agree_only_at_the_middle_of_the_seam_do_not_make_a_fold():
    from roof_measure.engine.edges import _planes_agree_pitched

    a = facet("L", [(0, 0), (5, 0), (5, 10), (0, 10)], (-0.5, 0, 5.5))  # z = 3 along the seam
    b = facet("H", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0.1, 0.0))  # 3 at the middle, 2.5 and 3.5 at the ends
    p0, p1 = np.array([5.0, 0.0]), np.array([5.0, 10.0])
    assert not _planes_agree_pitched(a, b, p0, p1, DEFAULT)  # a real step may hide at the ends
    b = facet("H", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0.0, 0.5))  # 3 along the whole seam
    assert _planes_agree_pitched(a, b, p0, p1, DEFAULT)
    flat = facet("F", [(5, 0), (10, 0), (10, 10), (5, 10)], (0, 0, 3.0))
    assert not _planes_agree_pitched(a, flat, p0, p1, DEFAULT)  # only two PITCHED facets fold


def test_a_pitched_roof_over_a_flat_deck_is_a_headwall_by_the_points_and_the_planes():
    flat = facet("F", [(0, 0), (5, 0), (5, 10), (0, 10)], (0, 0, 3.0))
    pitched = facet("P", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0, 1.0))  # 3.5 m at the seam: 0.5 m over the deck
    q = np.vstack([points_on(flat, 800, 1), points_on(pitched, 800, 2)])
    seam = _seams([flat, pitched], q)[("F", "P")]
    assert seam.type == "wall_flashing" and seam.upper == "P" and seam.jump_ft == pytest.approx(0.5 / 0.3048, abs=0.3)


# ---- the envelope (offline, the pipeline test's fakes)


def test_the_envelope_names_no_hints_and_the_parameter_hash_is_the_default(world, tmp_path):  # noqa: F811
    w = world(main="gable_d8")
    plain = run(w, tmp_path / "a")
    assert "hints" not in plain["model"]["source"]
    assert plain["model"]["quality"]["engine_params"] == DEFAULT.stable_hash()
    for i, h in enumerate((None, {})):
        env = run(w, tmp_path / f"b{i}", hints=h)
        assert "hints" not in env["model"]["source"]
        assert env["model"]["quality"]["engine_params"] == DEFAULT.stable_hash()
