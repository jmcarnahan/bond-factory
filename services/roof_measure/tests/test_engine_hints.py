"""Engine hints (``library.measure(..., hints=)``): ``{"steps": False}`` types a step line between two PITCHED facets whose
fitted planes agree at the seam from the planes. No hint (or a hint that is today's behaviour) changes nothing: the same
parameters hash, the same cache key. Synthetic data only."""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from test_engine_edges import CTX, facet, points_on
from test_pipeline_engine import no_network, run, world  # noqa: F401  (fixtures: the pipeline test's fakes)

from roof_measure import keys, library
from roof_measure.engine import hints as H
from roof_measure.engine.edges import build_edges
from roof_measure.engine.errors import Ctx
from roof_measure.engine.params import DEFAULT, HINT_FIELDS

# The default parameter hash is the key of every cached result: adding a hint field must never move it.
DEFAULT_HASH = "e0ff8f3ddc10638b75d4d7706c3b603794c85d8bb3656665e630f2fdcb64e991"
NO_STEPS = Ctx(DEFAULT.replace(pitched_steps=False), None)


def test_the_default_parameter_hash_never_changes():
    assert DEFAULT.stable_hash() == DEFAULT_HASH
    assert HINT_FIELDS == ("pitched_steps",)
    assert DEFAULT.replace(pitched_steps=False).stable_hash() != DEFAULT_HASH
    assert DEFAULT.replace(pitched_steps=True).stable_hash() == DEFAULT_HASH


@pytest.mark.parametrize("hints,same", [(None, True), ({}, True), ({"steps": True}, True), ({"steps": False}, False)])
def test_params_from_hints(hints, same):
    out = H.params_from_hints(hints)
    assert (out is DEFAULT) == same
    assert out.pitched_steps is (hints is None or hints.get("steps", True))


@pytest.mark.parametrize("hints,key", [({"nope": True}, "nope"), ({"steps": "no"}, "steps"), ({"steps": 0}, "steps"),
                                       ({"steps": None}, "steps"), ({"steps": False, "x": 1}, "x")])
def test_bad_hints_raise_naming_the_key(hints, key):
    with pytest.raises(ValueError, match=key):
        H.params_from_hints(hints)
    with pytest.raises(ValueError, match=key):
        H.clean_hints(hints)


def test_clean_hints_keeps_only_what_changes_something():
    assert H.clean_hints(None) is None and H.clean_hints({}) is None and H.clean_hints({"steps": True}) is None
    assert H.clean_hints({"steps": False}) == {"steps": False}


def _req(**extra):
    return {"method": "lidar_skeleton", "verify": False, "engine": "planes", "lat": 1.0, "lng": 2.0, **extra}


def test_cache_key_moves_only_for_a_hint_that_changes_something():
    base = keys.request_key(_req())
    assert base is not None
    for h in (None, {}, {"steps": True}):
        assert keys.request_key(_req(hints=h)) == base
    assert keys.request_key(_req(hints={"steps": False})) != base
    blocks = {"method": "lidar_skeleton", "verify": False, "engine": "blocks", "lat": 1.0, "lng": 2.0}
    assert keys.request_key({**blocks, "hints": {"steps": False}}) == keys.request_key(blocks)


def test_library_measure_takes_hints_and_rejects_bad_ones(tmp_path):
    assert "hints" in inspect.signature(library.measure).parameters
    with pytest.raises(ValueError, match="steps"):
        library.measure("", lat=1.0, lng=2.0, cache_dir=tmp_path, engine="planes", hints={"steps": "no"})
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


def _seams(facets, q, ctx):
    return {tuple(sorted(e.facets)): e for e in build_edges(facets, q, ctx) if len(e.facets) == 2}


def test_a_point_jump_beside_agreeing_planes_is_a_level_change_without_the_hint_and_a_valley_with_it():
    facets, q = _row()
    plain = _seams(facets, q, CTX)
    assert plain[('A', 'B')].type == "level_change" and plain[('C', 'D')].type == "level_change"
    hinted = _seams(facets, q, NO_STEPS)
    assert hinted[('A', 'B')].type == "valley" and hinted[('C', 'D')].type == "valley"
    assert hinted[('B', 'C')].type == "ridge"
    assert hinted[('A', 'B')].length_ft == pytest.approx(hinted[('C', 'D')].length_ft, rel=0.05)


def test_the_hint_changes_nothing_when_the_points_agree_with_the_planes():
    facets, q = _row(lift_b=0.0, lift_c=0.0)
    a = {k: e.type for k, e in _seams(facets, q, CTX).items()}
    b = {k: e.type for k, e in _seams(facets, q, NO_STEPS).items()}
    assert a == b == {('A', 'B'): "valley", ('B', 'C'): "ridge", ('C', 'D'): "valley"}


def test_a_real_step_between_pitched_roofs_stays_a_level_change_with_the_hint():
    low = facet("L", [(0, 0), (5, 0), (5, 10), (0, 10)], (-0.5, 0, 5.5))  # 3 m at the seam
    high = facet("H", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0, 1.0 + 0.5))  # 4 m at the seam: a 1 m wall
    q = np.vstack([points_on(low, 800, 1), points_on(high, 800, 2)])
    for ctx in (CTX, NO_STEPS):
        seam = _seams([low, high], q, ctx)[('H', 'L')]
        assert seam.type == "level_change"


def test_planes_that_agree_only_at_the_middle_of_the_seam_stay_a_level_change_with_the_hint():
    a = facet("L", [(0, 0), (5, 0), (5, 10), (0, 10)], (-0.5, 0, 5.5))  # z = 3 along the seam
    b = facet("H", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0.1, 0.0))  # 3 at the middle, 2.5 and 3.5 at the ends
    q = np.vstack([points_on(a, 800, 1), points_on(b, 800, 2, offset=0.5)])
    assert _seams([a, b], q, CTX)[("H", "L")].type == "level_change"
    assert _seams([a, b], q, NO_STEPS)[("H", "L")].type == "level_change"


def test_every_hint_field_keeps_its_default():
    """The hash skips a hint at its default: changing a default needs a PIPELINE_VERSION bump, so it must fail loudly here."""
    assert {n: getattr(DEFAULT, n) for n in HINT_FIELDS} == {"pitched_steps": True}


def test_flat_and_flat_pitched_seams_are_untouched_by_the_hint():
    flat = facet("F", [(0, 0), (5, 0), (5, 10), (0, 10)], (0, 0, 3.0))
    pitched = facet("P", [(5, 0), (10, 0), (10, 10), (5, 10)], (0.5, 0, 0.5))
    q = np.vstack([points_on(flat, 800, 1), points_on(pitched, 800, 2, offset=0.5)])
    assert {k: e.type for k, e in _seams([flat, pitched], q, CTX).items()} == \
        {k: e.type for k, e in _seams([flat, pitched], q, NO_STEPS).items()}


# ---- the envelope (offline, the pipeline test's fakes)


def test_the_envelope_names_the_hints_only_when_given(world, tmp_path):  # noqa: F811
    w = world(main="gable_d8")
    plain = run(w, tmp_path / "a")
    assert "hints" not in plain["model"]["source"]
    assert plain["model"]["quality"]["engine_params"] == DEFAULT.stable_hash()
    for i, h in enumerate((None, {}, {"steps": True})):
        env = run(w, tmp_path / f"b{i}", hints=h)
        assert "hints" not in env["model"]["source"]
        assert env["model"]["quality"]["engine_params"] == DEFAULT.stable_hash()
    hinted = run(w, tmp_path / "c", hints={"steps": False})
    assert hinted["model"]["source"]["hints"] == {"steps": False}
    assert hinted["model"]["quality"]["engine_params"] == DEFAULT.replace(pitched_steps=False).stable_hash()
    assert hinted["totals"] == plain["totals"]  # a plain gable has no step line: the answer is the same
