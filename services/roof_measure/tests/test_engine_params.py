"""EngineParams: frozen, hashable by value, every field covered by the hash."""

import dataclasses

import pytest

from roof_measure.engine.params import DEFAULT, EngineParams


def test_the_default_is_a_plain_instance_and_the_hash_is_stable():
    assert EngineParams() == DEFAULT
    assert EngineParams().stable_hash() == DEFAULT.stable_hash()
    assert len(DEFAULT.stable_hash()) == 64


def test_every_field_changes_the_hash():
    base = DEFAULT.stable_hash()
    for f in dataclasses.fields(DEFAULT):
        v = getattr(DEFAULT, f.name)
        if isinstance(v, bool):
            new = not v
        elif isinstance(v, (int, float)):
            new = v + 1
        else:
            new = tuple(x + 1 for x in v)
        assert DEFAULT.replace(**{f.name: new}).stable_hash() != base, f.name


def test_it_is_frozen_and_replace_rejects_unknown_names():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.s3_axis = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        DEFAULT.replace(no_such_tunable=1)


def test_the_plan_numbers_are_the_defaults():
    p = DEFAULT
    assert (p.overhang_scale_draw, p.overhang_scale_roofedge) == (1.0, 0.25)
    assert (p.s2_steep_rise, p.s2_strip_width, p.s2_patch_area, p.s2_patch_rms, p.s2_patch_pitch) == (2.0, 1.5, 15.0, 0.05, 2.0)
    assert (p.s3_axis, p.s3_snap_az) == (True, 10.0)
    assert (p.s4_gentle, p.s4_keep_area, p.s4_rms, p.s4_pts) == (True, 1.5, 0.05, 12)
    assert (p.density_refuse, p.density_ok, p.fit_floor, p.supported_floor) == (4.0, 6.0, 0.55, 70.0)
    assert (p.mismatch_lo, p.mismatch_hi, p.mismatch_shift) == (0.70, 1.30, 0.17)


# The default parameter hash is the key of every cached result: a deliberate change re-pins it (and bumps PIPELINE_VERSION).
DEFAULT_HASH = "e59af970af4c6b435ec90349929abf2a62b94c35a41d90bc99965e4b9c174802"


def test_the_default_parameter_hash_is_pinned():
    assert DEFAULT.stable_hash() == DEFAULT_HASH
