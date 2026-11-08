"""Synthetic inputs and fixture generation (not part of the measuring pipeline).

WHY: the model builder needs inputs with known closed-form answers (a hip, a gable, a flat
roof with parapet) and a stand-in for the LiDAR block file until the data layer delivers the
real one. Everything here goes through the same ``classify`` / ``build_model`` code as real data.

Run ``python -m roof_measure.synth [fixtures_dir]`` to regenerate the four model fixtures;
``python -m roof_measure.synth --site1-blocks outline.geojson`` rewrites the hand-crafted blocks file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import LineString, Polygon, box
from shapely.geometry import shape as shp_shape
from shapely.ops import split as shp_split

from .classify import Block, BlockSet, RoofBlock, classify_blocks, ring_of
from .frame import Frame
from .model import build_model, write_model
from .skeleton import hip_roof_edges

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
# The real site 1 address and coordinates live in local/sites.json (untracked). Fixtures carry placeholders:
# the frame sits at lat 0 / lng 0 (UTM 31N), so Solar rows and blocks stay mutually consistent.
SITE1_ADDRESS = {"line1": "100 Example Ave", "city": "Sampletown", "state": "CA", "zip": "90000",
                 "formatted": "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"}
SITE1_FRAME = {"epsg": 32631, "x0_m": 166021.443, "y0_m": 0.0}


# ----------------------------------------------------------------------------- closed-form cases
def _plain_blockset(label: str, ring: list[tuple[float, float]]) -> BlockSet:
    return BlockSet(address={"line1": label, "city": "", "state": "", "zip": "", "formatted": label},
                    origin={"lat": 0.0, "lng": 0.0}, frame={"epsg": 32611, "x0_m": 0.0, "y0_m": 0.0},
                    footprint_ft=ring, footprint_meta={"provider": "synthetic", "id": label,
                                                       "area_sqft": Polygon(ring).area})


def synthetic_hip() -> tuple[BlockSet, list[RoofBlock]]:
    """35 x 26 ft hip at 4/12: eaves 122, ridge 9, hips 75.55, area 959.22 (closed form)."""
    ring = [(0.0, 0.0), (35.0, 0.0), (35.0, 26.0), (0.0, 26.0)]
    return (_plain_blockset("Synthetic hip 35 x 26 ft at 4/12", ring),
            [RoofBlock(id="b1", form="hip", polygon=ring, pitch_rise=4.0, ridge_azimuth_deg=90.0,
                       level_ft=0.0, eave_height_ft=10.0)])


def synthetic_gable() -> tuple[BlockSet, list[RoofBlock]]:
    """40 x 24 ft gable at 6/12, short ends are gables: eaves 80, ridge 40, rakes 4 x 12 x sf."""
    ring = [(0.0, 0.0), (40.0, 0.0), (40.0, 24.0), (0.0, 24.0)]
    return (_plain_blockset("Synthetic gable 40 x 24 ft at 6/12", ring),
            [RoofBlock(id="b1", form="gable", polygon=ring, pitch_rise=6.0, gable_edges=[1, 3],
                       ridge_azimuth_deg=90.0, level_ft=0.0, eave_height_ft=10.0)])


def synthetic_flat_parapet() -> tuple[BlockSet, list[RoofBlock]]:
    """60 x 40 ft flat roof: area 2400, parapet 200 on every outline edge."""
    ring = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
    return (_plain_blockset("Synthetic flat roof 60 x 40 ft with parapet", ring),
            [RoofBlock(id="b1", form="flat", polygon=ring, level_ft=0.0, eave_height_ft=12.0)])


# ----------------------------------------------------------------------------- Site1 stand-in
def _site1_footprint(geojson: Path) -> tuple[Frame, Polygon]:
    g = shp_shape(json.loads(geojson.read_text())["features"][0]["geometry"])
    frame, fp_m = Frame.for_footprint(g)
    ft = frame.to_ft(np.array(fp_m.exterior.coords))
    return frame, Polygon([tuple(p) for p in ft]).buffer(0)


def site1_blocks_handmade(footprint_geojson: Path) -> BlockSet:
    """Hand-crafted ``bond.roof_blocks`` for the sample building from the research numbers.

    NOT real LiDAR output: four hip faces at about 3.9/12 forming a 35 x 27 ft hip at the west
    end, four flat strips tiling the rest (shrunk 1.2 ft and with a notch cut so the gap fill is
    exercised) and three awnings on the south outline. Levels follow the research finding that
    all flats sit within 0.3 ft of one level and the hip eave is at that level.
    """
    _frame, fp = _site1_footprint(footprint_geojson)
    flat_z, ground_z = 131.2, 108.3  # ft; ~40.0 m roof, ~33 m terrain
    hip_zone = fp.intersection(box(-1, 28.5, 35.4, 60))
    rect = hip_zone.minimum_rotated_rectangle
    rect_pts = [tuple(p) for p in list(rect.exterior.coords)[:-1]]
    geom = hip_roof_edges(rect_pts, 3.9)
    blocks: list[Block] = []
    faces = {}
    for f in geom["facets"]:
        poly = Polygon(f["polygon_xy"]).intersection(fp).buffer(-0.8)
        faces[f["aspect_deg"]] = (f, poly)
    flat_area = fp.difference(rect).difference(unary_awnings(fp))
    # four vertical strips of the flat remainder
    cuts = [50.0, 85.0, 125.0]
    parts = [flat_area]
    for x in cuts:
        nxt = []
        for p in parts:
            if p.bounds[0] < x < p.bounds[2]:
                pieces = [g for g in shp_split(p, LineString([(x, -50), (x, 200)])).geoms]
                nxt.extend(pieces)
            else:
                nxt.append(p)
        parts = nxt
    parts = sorted(parts, key=lambda g: g.centroid.x)
    zs = [flat_z, flat_z - 0.2, flat_z + 0.1, flat_z - 0.1]
    for i, (p, z) in enumerate(zip(parts[:4], zs, strict=False)):
        shrunk = p.buffer(-1.2)
        if i == 1:  # a tree-covered patch: no points
            shrunk = shrunk.difference(box(shrunk.centroid.x - 6, shrunk.centroid.y - 4,
                                           shrunk.centroid.x + 6, shrunk.centroid.y + 4))
        for q in ([shrunk] if shrunk.geom_type == "Polygon" else list(shrunk.geoms)):
            if q.area < 20:
                continue
            blocks.append(Block(id=f"k{len(blocks)}", kind="flat", polygon_ft=ring_of(q, 0.05),
                                plan_area_sqft=q.area, mean_z_ft=z, height_above_ground_ft=z - ground_z,
                                pitch_rise=0.2, aspect_deg=None, rms_ft=0.07, n_cells=int(q.area * 10.7 / 4)))
    for asp, (f, poly) in sorted(faces.items()):
        mz = flat_z + _centroid_height(f)
        blocks.append(Block(id=f"k{len(blocks)}", kind="sloped", polygon_ft=ring_of(poly, 0.05),
                            plan_area_sqft=poly.area, mean_z_ft=mz, height_above_ground_ft=mz - ground_z,
                            pitch_rise=3.9, aspect_deg=round(asp, 1), rms_ft=0.1, n_cells=int(poly.area * 2.7)))
    for aw in awnings(fp):
        shrunk = aw.buffer(-0.5)
        blocks.append(Block(id=f"k{len(blocks)}", kind="sloped", polygon_ft=ring_of(shrunk, 0.05),
                            plan_area_sqft=shrunk.area, mean_z_ft=flat_z - 2.8,
                            height_above_ground_ft=flat_z - 2.8 - ground_z, pitch_rise=3.85, aspect_deg=180.0,
                            rms_ft=0.12, n_cells=int(shrunk.area * 1.5)))
    polys = {b.id: b.poly for b in blocks}
    borders = []
    ids = list(polys)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            d = polys[a].distance(polys[b])
            if d <= 3.5:
                ba, bb = next(x for x in blocks if x.id == a), next(x for x in blocks if x.id == b)
                borders.append({"a": a, "b": b, "length_ft": round(float(max(
                    polys[a].buffer(2.0).intersection(polys[b]).length / 2, 0.0)), 2),
                    "step_ft": round(bb.mean_z_ft - ba.mean_z_ft, 2)})
    outline = [{"block": b.id, "length_ft": round(float(b.poly.boundary.intersection(fp.exterior.buffer(0.6)).length), 2)}
               for b in blocks]
    return BlockSet(
        address=SITE1_ADDRESS, origin={"lat": 0.0, "lng": 0.0}, frame=dict(SITE1_FRAME),
        footprint_ft=[tuple(p) for p in ring_of(fp, 0.0)],
        footprint_meta={"provider": "lacounty_lariac_2020", "id": "SITE1-BLDG", "area_sqft": 6901.0,
                        "height_ft": 29.21},
        lidar={"project": "CA_LosAngeles_1_B23", "acquired": "2023-10-03/2023-12-08", "year": 2023,
               "points_on_roof": 12049, "density_per_m2": 19.0, "ground_z_m": ground_z * 0.3048, "epsg": SITE1_FRAME["epsg"]},
        blocks=blocks, borders=borders, outline_edges=outline,
        extra={"_synthetic": True,
               "note": "HAND-CRAFTED from research numbers (hip 35x27 ft at 3.9/12 at the west end, 4 flat "
                       "blocks, 3 south awnings). Not real LiDAR output; replaced when the data layer delivers."})


def _centroid_height(f: dict[str, Any]) -> float:
    poly = Polygon(f["polygon_xy"])
    c = poly.centroid
    a, b, d = f["plane"]
    return float(a + b * c.x + d * c.y)


def awnings(fp: Polygon) -> list[Polygon]:
    """Three ~9.5 x 8.5 ft awnings on the south outline (x 84-93.5, 96-105.5, 118-127.5)."""
    out = []
    for x0 in (84.0, 96.0, 118.0):
        strip = fp.intersection(box(x0, -5, x0 + 9.5, 100))
        ymin = strip.bounds[1]
        out.append(strip.intersection(box(x0, ymin - 1, x0 + 9.5, ymin + 8.6)))
    return out


def unary_awnings(fp: Polygon) -> Polygon:
    from shapely.ops import unary_union
    return unary_union(awnings(fp))


# ----------------------------------------------------------------------------- generation
def generate_fixtures(out_dir: Path = FIXTURES, site1_blocks: Path | None = None) -> dict[str, dict[str, Any]]:
    """Write the three closed-form fixtures and ``site1_lidar.json``; returns the models."""
    out_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, dict[str, Any]] = {}
    for name, fn in (("synthetic_hip", synthetic_hip), ("synthetic_gable", synthetic_gable),
                     ("synthetic_flat_parapet", synthetic_flat_parapet)):
        bs, rbs = fn()
        model = build_model(bs, rbs, {"method": "fixture"})
        write_model(model, out_dir / f"{name}.json")
        made[name] = model
    path = site1_blocks or out_dir / "site1_blocks.json"
    bs = BlockSet.load(path)
    cl = classify_blocks(bs)
    model = build_model(bs, cl.blocks, {"method": "lidar_skeleton"}, cl)
    write_model(model, out_dir / "site1_lidar.json")
    made["site1_lidar"] = model
    return made


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "--site1-blocks":
        if len(args) < 2:
            print("skipped: pass the building outline GeoJSON, e.g. --site1-blocks path/to/bldg.geojson")
            return
        dest = Path(__file__).resolve().parents[1] / "tests" / "data" / "site1_blocks_handmade.json"
        site1_blocks_handmade(Path(args[1])).save(dest)
        print("wrote", dest)
        return
    out = Path(args[0]) if args else FIXTURES
    for name, m in generate_fixtures(out).items():
        t = m["totals"]
        print(f"{name}: total {t['total_area_sqft']:.2f} sqft, lengths {({k: round(v, 2) for k, v in t['lengths_ft'].items() if v})}")


if __name__ == "__main__":
    main()
