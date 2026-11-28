"""The plane engine's example envelope (``roof_engine/roof_measurement_0.4_engine.json``), built from a SYNTHETIC roof.

``flat_pitched_step`` (a flat part, a gable and a 0.6 m step between them) at 8 points/m2 goes through the real engine,
the real adapter and ``build_envelope``: every contract-0.4 key a reader can meet is in the file. Nothing here is a real
place: the address is the placeholder one, the origin is an invented grid point, the parcel and outline ids say SYNTH. Deterministic.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .blockset import BlockSet

EPSG = 32631  # the zone whose grid holds the null island of the placeholder fixtures (origin 0, 0)
STAMP = "2026-11-22T00:00:00Z"
CASE = "flat_pitched_step_d8"
ADDRESS = {"line1": "100 Example Ave", "city": "Sampletown", "state": "CA", "zip": "90000",
           "formatted": "100 Example Ave, Sampletown, CA 90000"}


def engine_envelope() -> dict[str, Any]:
    """The 0.2 envelope with the 0.4 additions for the synthetic roof."""
    from .engine import measure_roof, synth_points
    from .engine.load import roof_points_from_arrays
    from .pipeline_engine import build_result

    case = next(c for c in synth_points.cases() if c.name == CASE)
    pts = case.points()
    wall = case.roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    res = measure_roof(rp, wall, outline_source="lacounty_lariac_2020", parcel_match="exact", context=pts)
    from pyproj import Transformer

    x0, y0 = Transformer.from_crs(4326, EPSG, always_xy=True).transform(0.0, 0.0)  # the frame origin IS lat 0, lng 0
    base = BlockSet(address=dict(ADDRESS), origin={"lat": 0.0, "lng": 0.0},
                    frame={"epsg": EPSG, "x0_m": round(x0, 4), "y0_m": round(y0, 4)},
                    footprint_ft=[], footprint_meta={"provider": "lacounty_lariac_2020", "id": "SYNTH-B1",
                                                     "area_sqft": round(wall.area * 10.7639, 1)})
    lidar_meta = {"project": "SYNTHETIC", "acquired": "2026-01-01", "year": 2026, "points_on_roof": int(rp.n_on_roof),
                  "density_per_m2": 8.0, "ground_z_m": 0.0, "epsg": EPSG}
    fpinfo = {"source": "lariac", "warnings": [], "codes": [], "other_buildings": 0, "match": "exact",
              "building": {"parcel_id": "SYNTH-P1", "outline_id": "SYNTH-B1", "outline_centroid": [0.0, 0.0],
                           "chosen_by": "auto"},
              "nearby_buildings": [{"outline_id": "SYNTH-B2", "area_sqft": 420.0, "distance_m": 14.2, "on_matched_parcel": True},
                                   {"outline_id": "SYNTH-B3", "area_sqft": 1180.0, "distance_m": 41.0, "on_matched_parcel": False}]}
    with tempfile.TemporaryDirectory() as tmp:
        env = build_result(res, rp.ground_z, lidar_meta, base, fpinfo, Path(tmp), "synthetic").envelope
    env["generated_at"] = env["model"]["generated_at"] = STAMP
    return env
