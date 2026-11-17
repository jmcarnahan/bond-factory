"""A big section partitioned part by part (planes_envelope_split): parts meet in valleys, each part is a lower
envelope and the roof is the higher part where two meet. Synthetic, as test_planes_envelope.py.
"""

from __future__ import annotations

from shapely.geometry import LineString
from test_planes_envelope import to_local
from test_planes_envelope_pins import house_like

import roof_measure.planes_envelope as pe
from roof_measure.planes_envelope_geom import eq_of
from roof_measure.planes_envelope_lines import neighbours
from roof_measure.planes_envelope_split import subsections


def test_parts_are_joined_by_ridges_hips_and_seams_and_split_at_valleys():
    planes, raw, _fp = house_like()
    shapes = [p.shape() for p in planes]
    raws = [raw[p.id] for p in planes]
    groups = subsections(list(range(len(planes))), neighbours(shapes), [eq_of(p) for p in planes], raws, shapes)
    ids = sorted(sorted(planes[k].id for k in g) for g in groups)
    front, rear = ["k0", "k2", "k6"], ["k1", "k4", "k5", "k7"]
    assert front in ids and rear in ids  # front and rear, the long valley between them (k3: its tapering step)


def test_split_partition_keeps_the_valley_between_the_parts_straight(monkeypatch):
    monkeypatch.setattr(pe, "SPLIT_MIN_PLANES", 3)
    planes, raw, fp = house_like()
    res = pe._run(planes, raw, fp, split=True)
    assert res.gate_failure is None, res.gate_failure
    assert len({s.get("part") for s in res.sections}) >= 2  # partitioned part by part
    valley = [to_local(LineString(b["segment"])) for b in res.borders
              if b["kind"] == "valley" and {b["a"], b["b"]} & {"k4", "k5"}]
    assert sum(v.length for v in valley) > 15.0  # (the normal partition draws all 30 ft: this is only a retry)
    assert all(abs(y - 30.0) < 0.6 for v in valley for _, y in v.coords)  # where the front and rear slopes meet
    ridge = [to_local(LineString(b["segment"])) for b in res.borders if {b["a"], b["b"]} == {"k0", "k2"}]
    assert ridge and all(abs(y - 16.0) < 0.6 for r in ridge for _, y in r.coords)


def test_the_split_retry_is_only_tried_when_the_normal_partition_fails(monkeypatch):
    planes, raw, fp = house_like()  # 8 planes in one section, passes as it is
    calls = []
    real = pe._run

    def spy(*a, **k):
        calls.append(k.get("split", False))
        return real(*a, **k)

    monkeypatch.setattr(pe, "_run", spy)
    monkeypatch.setattr(pe, "SPLIT_MIN_PLANES", 3)
    assert pe.envelope_detail(planes, raw, fp).gate_failure is None
    assert calls == [False]
