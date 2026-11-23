"""Extra synthetic roofs for the engine's failure classes: low slope, multi-level flat roofs, flat junk.

Built from the same wing model as ``synth_points`` (a roof is the maximum over wings, so a small flat wing with a higher
eave is a bulkhead, a thin raised strip is a parapet). Dimensions are feet in the plan and metres in height, pitch is rise
per 12. ``extra_cases()`` returns ``SynthCase`` objects named ``<shape>_d<density>`` like ``synth_points.cases()``; the
harness (``tools.roof_eval.synth``) can take them through ``with_extra`` and so can the tests.
"""

from __future__ import annotations

from .synth_points import EAVE_M, OVERHANG_M, SynthCase, _roof, _wing, cross_gable, gable, hip, l_shape, shed
from .synth_shapes import M2FT, SynthRoof, Wing

_OVH_FT = OVERHANG_M * M2FT  # the generator cannot make a facet with a hole: raised parts reach out to the roof edge

LOW_PITCHES = (2.5, 3.0)
NOISY_SIGMA_M = 0.07  # vertical noise of the "noisy" variants (real airborne returns scatter 5-10 cm; the generator default is 3 cm)


def _flat_wing(rect_ft, eave_m: float, ovh_m: float = OVERHANG_M, no_ovh: str = "") -> Wing:
    return _wing(rect_ft, "", 0.0, eave_m, ovh_m, no_ovh)


def two_level_flat(length_ft=36.0, width_ft=26.0, step_m=1.0, eave_m=EAVE_M, rotation_deg=0.0) -> SynthRoof:
    """Two flat roofs side by side; the east one is ``step_m`` higher (a wall between them)."""
    half = length_ft / 2
    w = [_flat_wing((0, 0, half, width_ft), eave_m, no_ovh="E"),
         _flat_wing((half, 0, length_ft, width_ft), eave_m + step_m, no_ovh="W")]
    return _roof("two_level_flat", w, rotation_deg, step_m=step_m)


def flat_parapet(length_ft=40.0, width_ft=30.0, height_m=0.3, strip_ft=1.2, eave_m=EAVE_M, rotation_deg=0.0) -> SynthRoof:
    """A flat roof with a low parapet strip on three sides (raised ``height_m``, ``strip_ft`` wide, out to the roof edge; a
    fourth side would close a ring and leave the strip facet with a hole)."""
    w = [_flat_wing((0, 0, length_ft, width_ft), eave_m)]
    o, z = _OVH_FT, eave_m + height_m
    s = strip_ft
    for rect in ((-o, -o, length_ft + o, s), (-o, width_ft - s, length_ft + o, width_ft + o), (-o, s, s, width_ft - s)):
        w.append(_flat_wing(rect, z, ovh_m=0.0))
    return _roof("flat_parapet", w, rotation_deg)


def flat_equipment(length_ft=44.0, width_ft=30.0, eave_m=EAVE_M, rotation_deg=0.0) -> SynthRoof:
    """A flat roof with rooftop units (1 m high, 4 x 4 ft and 4 x 3 ft) and a stair bulkhead (2.4 m, 6.5 x 6.5 ft: under 6 m2), each
    against the roof edge (a box in the middle would leave a hole in the main facet, which the generator cannot make)."""
    o = _OVH_FT
    w = [_flat_wing((0, 0, length_ft, width_ft), eave_m),
         _flat_wing((10, -o, 14, 4), eave_m + 1.0, ovh_m=0.0), _flat_wing((24, width_ft - 3, 28, width_ft + o), eave_m + 1.0, ovh_m=0.0),
         _flat_wing((length_ft - 6.5, -o, length_ft + o, 6.5), eave_m + 2.4, ovh_m=0.0)]
    return _roof("flat_equipment", w, rotation_deg)


def double_gable(pitch_a: float = 2.2, pitch_b: float = 3.7, length_ft=40.0, width_ft=22.0, eave_m=EAVE_M,
                 rotation_deg=0.0) -> SynthRoof:
    """Two parallel gables side by side (south one at ``pitch_a``, north one at ``pitch_b``, the valley between): four
    low-slope facets, opposing normals only 25-35 degrees apart (the pattern of a real low-slope double-gable roof)."""
    w = [_wing((0, 0, length_ft, width_ft), "SN", pitch_a, eave_m, OVERHANG_M, no_ovh="N"),
         _wing((0, width_ft, length_ft, 2 * width_ft), "SN", pitch_b, eave_m, OVERHANG_M, no_ovh="S")]
    return _roof("double_gable", w, rotation_deg)


def flat_pair(pitch: float = 1.5, rotation_deg=0.0) -> SynthRoof:
    """A gable at ``pitch`` below the 2/12 flat cut: truth facets are flat, each side of the ridge."""
    return gable(pitch=pitch, rotation_deg=rotation_deg)


def _shapes() -> dict[str, SynthRoof]:
    out: dict[str, SynthRoof] = {}
    for p in LOW_PITCHES:
        tag = f"p{round(p * 10)}"
        out[f"gable_{tag}"] = gable(pitch=p)
        out[f"hip_{tag}"] = hip(pitch=p)
        out[f"l_shape_{tag}"] = l_shape(pitch=p)
        out[f"cross_gable_{tag}"] = cross_gable(pitch=p)
    out["shed_p25"] = shed(pitch=2.5)
    out["gable_p15"] = flat_pair(1.5)
    out["double_gable"] = double_gable()
    out["hip_p15"] = hip(pitch=1.5)
    out["two_level_flat"] = two_level_flat()
    out["flat_parapet"] = flat_parapet()
    out["flat_equipment"] = flat_equipment()
    return out


def extra_cases(densities: tuple[int, ...] = (16, 8)) -> list[SynthCase]:
    """Every extra shape at each density (seed 1), plus rotated (17 deg) low-slope and two-level copies at 8 pts/m2."""
    cases = [SynthCase(f"{n}_d{d}", r, {"density": d, "seed": 1}) for n, r in _shapes().items() for d in densities]
    for n, r in (("gable_p25", gable(pitch=2.5)), ("hip_p30", hip(pitch=3.0)), ("l_shape_p30", l_shape(pitch=3.0)),
                 ("two_level_flat", two_level_flat()), ("flat_equipment", flat_equipment())):
        cases.append(SynthCase(f"{n}_d8_noisy", r, {"density": 8, "seed": 6, "noise_sigma_m": NOISY_SIGMA_M}))
    cases.append(SynthCase("gable_p25_d8_rot17", gable(pitch=2.5, rotation_deg=17.0), {"density": 8, "seed": 5}))
    cases.append(SynthCase("hip_p30_d8_rot17", hip(pitch=3.0, rotation_deg=17.0), {"density": 8, "seed": 5}))
    cases.append(SynthCase("two_level_flat_d8_rot17", two_level_flat(rotation_deg=17.0), {"density": 8, "seed": 5}))
    return cases


def with_extra(base: dict[str, SynthCase], densities: tuple[int, ...] = (16, 8)) -> dict[str, SynthCase]:
    """``base`` (name -> case, as the harness builds it) plus the extra cases."""
    return {**base, **{c.name: c for c in extra_cases(densities)}}
