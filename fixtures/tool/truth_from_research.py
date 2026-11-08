#!/usr/bin/env python3
"""Build fixtures/site1_truth.json (schema bond.roof_model/0.1) from the
ground-truth research files for the site 1 sample, then validate it.

Usage (needs shapely; run with -I so nothing is picked up from the cwd):

    python -I fixtures/tool/truth_from_research.py \
        --research /path/to/roof-poc/ground-truth \
        --out fixtures/site1_truth.json

Inputs (read only): plan.geojson, length_report.json, area_report.json.
The geojson is a photo reconstruction (3 to 5 percent error, not
orthogonalised). Printed Roofr totals are authoritative and are copied, not
recomputed. Edge lengths use the printed label where one exists, else the
geometric length of the reconstruction.
"""
import argparse
import json
import math
import os
import sys
from collections import OrderedDict

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

TYPES = ["eave", "rake", "ridge", "hip", "valley", "step_flashing",
         "wall_flashing", "parapet", "transition", "unspecified"]
# geojson category -> contract edge type
CAT = {"eaves": "eave", "hips": "hip", "ridges": "ridge", "parapet": "parapet",
       "parapet+rakes": "parapet"}
HIP_PITCH = 3.9          # LiDAR plane fit; research derived ~5/12 (4.5 to 6.5)
AWNING_PITCH = 3.9       # sloped, treated as shed at the hip pitch
RAKE_RUN_FT = 7.5        # lower, free run of an awning side (research saw ~6 ft)
HIP_ASPECT = {"hip_N": 0, "hip_E": 90, "hip_S": 180, "hip_W": 270}
BLOCK_SUFFIX = {"flat151": "Flat 151", "flat2121": "Flat 2,121",
                "flat1013": "Flat 1,013", "flat922": "Flat 922"}
PRINTED = {"eave": 209 + 8 / 12, "rake": 32.0, "ridge": 7 + 9 / 12,
           "hip": 76 + 2 / 12, "valley": 0.0, "step_flashing": 50.0,
           "wall_flashing": 344 + 5 / 12, "parapet": 423 + 10 / 12,
           "transition": 0.0, "unspecified": 0.0}


def d(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def split_polyline(pts, printed):
    """Two-point segments; printed length (or None) distributed by length."""
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    geo = [d(a, b) for a, b in segs]
    tot = sum(geo)
    out = []
    for (a, b), g in zip(segs, geo):
        ln = printed * g / tot if printed is not None else g
        out.append(([list(a), list(b)], ln))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--research", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gj = json.load(open(os.path.join(args.research, "plan.geojson")))
    lr = json.load(open(os.path.join(args.research, "length_report.json")))
    ar = json.load(open(os.path.join(args.research, "area_report.json")))
    lt = lr["says"]["legend_totals"]
    at = ar["says"]["totals_sqft"]
    for k, key in [("eave", "eaves"), ("rake", "rakes"), ("ridge", "ridges"),
                   ("hip", "hips"), ("valley", "valleys"),
                   ("step_flashing", "step_flashing"),
                   ("wall_flashing", "wall_flashing"),
                   ("parapet", "parapet_wall"), ("transition", "transitions"),
                   ("unspecified", "unspecified")]:
        if key in lt:
            PRINTED[k] = lt[key]["decimal_ft"]

    feats = gj["features"]
    facet_f = [f for f in feats if f["properties"]["kind"] == "facet"]
    edge_f = [f for f in feats if f["properties"]["kind"] == "edge"]
    hole_f = [f for f in feats if f["properties"]["kind"] == "excluded_dashed_rect"]

    def ring(f):
        r = f["geometry"]["coordinates"][0]
        return [list(p) for p in r[:-1]]

    # ---- facets and blocks -------------------------------------------------
    facets, blocks = [], []
    fid = {}          # geojson id -> facet id
    shapes = {}       # facet id -> shapely polygon
    props = {f["properties"]["id"]: f["properties"] for f in facet_f}
    geo = {f["properties"]["id"]: ring(f) for f in facet_f}

    hip_ids = ["hip_N", "hip_E", "hip_S", "hip_W"]
    hip_union = unary_union([Polygon(geo[i]) for i in hip_ids]).buffer(0.02).buffer(-0.02)
    hip_poly = [list(p) for p in hip_union.exterior.coords[:-1]]
    blocks.append({"id": "b1", "form": "hip", "polygon": hip_poly,
                   "pitch_rise": HIP_PITCH, "ridge_azimuth_deg": 90,
                   "gable_edges": [], "eave_height_ft": None,
                   "plan_area_sqft": hip_union.area})
    n = 1
    for i in hip_ids:
        n_id = "f%d" % n
        fid[i] = n_id
        facets.append({"id": n_id, "block": "b1", "kind": "sloped",
                       "polygon": geo[i], "pitch_rise": HIP_PITCH,
                       "aspect_deg": HIP_ASPECT[i], "plan_area_sqft": None,
                       "area_sqft": float(props[i]["reported_area_sqft"])})
        n += 1
    bn = 2
    for i in ["awn82", "awn87", "awn86"]:
        b_id, n_id = "b%d" % bn, "f%d" % n
        fid[i] = n_id
        poly = geo[i]
        blocks.append({"id": b_id, "form": "shed", "polygon": poly,
                       "pitch_rise": AWNING_PITCH, "ridge_azimuth_deg": 90,
                       "gable_edges": [], "eave_height_ft": None,
                       "plan_area_sqft": Polygon(poly).area})
        facets.append({"id": n_id, "block": b_id, "kind": "sloped",
                       "polygon": poly, "pitch_rise": AWNING_PITCH,
                       "aspect_deg": 180, "plan_area_sqft": None,
                       "area_sqft": float(props[i]["reported_area_sqft"])})
        bn += 1
        n += 1
    for i in ["flat151", "flat2121", "flat1013", "flat922"]:
        b_id, n_id = "b%d" % bn, "f%d" % n
        fid[i] = n_id
        poly = geo[i]
        blocks.append({"id": b_id, "form": "flat", "polygon": poly,
                       "pitch_rise": 0.0, "ridge_azimuth_deg": None,
                       "gable_edges": [], "eave_height_ft": None,
                       "plan_area_sqft": Polygon(poly).area})
        facets.append({"id": n_id, "block": b_id, "kind": "flat",
                       "polygon": poly, "pitch_rise": 0.0, "aspect_deg": None,
                       "plan_area_sqft": None,
                       "area_sqft": float(props[i]["reported_area_sqft"])})
        bn += 1
        n += 1
    for f in facets:
        shapes[f["id"]] = Polygon(f["polygon"])

    # ---- holes (the dashed openings) --------------------------------------
    holes = []
    hole_edges = []   # (type, points, length, facet ids)
    for k, f in enumerate(hole_f, 1):
        p = ring(f)
        poly = Polygon(p)
        host = [fi for fi, s in shapes.items() if s.contains(poly.centroid)]
        if not host:
            host = [min(shapes, key=lambda fi: shapes[fi].distance(poly.centroid))]
        cat = f["properties"]["category"]
        etype = "step_flashing" if cat == "step_flashing" else "wall_flashing"
        holes.append({"id": "h%d" % k, "kind": "chimney", "polygon": p,
                      "area_sqft": poly.area, "_host": host[0],
                      "_src": f["properties"]["id"]})
        for j in range(4):
            a, b = p[j], p[(j + 1) % 4]
            hole_edges.append((etype, [a, b], d(a, b), [host[0]]))
    for fct in facets:
        inside = sum(h["area_sqft"] for h in holes if h["_host"] == fct["id"])
        fct["plan_area_sqft"] = shapes[fct["id"]].area - inside

    # ---- edges -------------------------------------------------------------
    edges = []

    def link(pts):
        """Facets whose boundary runs along this segment (at most two)."""
        ln = LineString(pts)
        buf = ln.buffer(0.9)
        sc = []
        for fi, s in shapes.items():
            ov = s.boundary.intersection(buf).length
            if ov >= 0.5 * ln.length:
                sc.append((ov, fi))
        sc.sort(reverse=True)
        return [fi for _, fi in sc[:2]]

    def add(etype, pts, ln, facet_ids=None, note=None):
        edges.append({"id": "e%d" % (len(edges) + 1), "type": etype,
                      "points": pts, "length_ft": ln,
                      "facets": facet_ids if facet_ids else link(pts),
                      "_note": note})

    for f in edge_f:
        p = f["properties"]
        if p["id"].startswith("awn"):
            continue            # awning sides are handled below
        printed = p["printed_ft"]
        if p["category"] == "ridges":
            printed = PRINTED["ridge"]
        for pts, ln in split_polyline(f["geometry"]["coordinates"], printed):
            add(CAT[p["category"]], pts, ln, note=p["id"])

    # awnings: polygon is [TL, TR, BR, BL] (top is the wall side, bottom free)
    lab = {p["properties"]["id"]: p["properties"]["printed_ft"] for p in edge_f}
    spec = {  # geojson id -> (left label id, left split, right split)
        "awn82": ("awn1_left11", False, True),
        "awn87": ("awn2_left11", True, True),
        "awn86": ("awn3_left11", True, False),
    }
    for gid, (lid, lsplit, rsplit) in spec.items():
        TL, TR, BR, BL = geo[gid]
        fac = [fid[gid]]
        add("parapet", [TL, TR], d(TL, TR), fac, gid + " top (unlabelled)")
        add("eave", [BR, BL], d(BR, BL), fac, gid + " bottom (unlabelled)")
        for side, (top, bot), do_split, printed in [
                ("left", (TL, BL), lsplit, lab[lid]),
                ("right", (TR, BR), rsplit, None)]:
            L = d(top, bot)
            if not do_split:
                add("parapet", [list(top), list(bot)],
                    printed if printed is not None else L, fac,
                    "%s %s side" % (gid, side))
                continue
            t = RAKE_RUN_FT / L
            mid = [bot[0] + (top[0] - bot[0]) * t, bot[1] + (top[1] - bot[1]) * t]
            scale = (printed / L) if printed is not None else 1.0
            add("parapet", [list(top), mid], (L - RAKE_RUN_FT) * scale, fac,
                "%s %s side upper (wall side)" % (gid, side))
            add("rake", [mid, list(bot)], RAKE_RUN_FT * scale, fac,
                "%s %s side lower free run" % (gid, side))

    # unlabelled outline of the flat roofs (steps, jogs, short walls)
    cover = unary_union([LineString(e["points"]).buffer(0.9) for e in edges])
    outline = unary_union([s.buffer(0.6) for s in shapes.values()]).buffer(-0.6).boundary
    derived = []
    for fi, s in shapes.items():
        if [f for f in facets if f["id"] == fi][0]["kind"] != "flat":
            continue
        c = list(s.exterior.coords)
        for a, b in zip(c[:-1], c[1:]):
            seg = LineString([a, b])
            rest = seg.difference(cover)
            parts = [rest] if rest.geom_type == "LineString" else list(getattr(rest, "geoms", []))
            for part in parts:
                if part.is_empty or part.length < 1.5:
                    continue
                if part.interpolate(0.5, normalized=True).distance(outline) > 1.0:
                    continue    # interior flat-to-flat line, not drawn as parapet
                pts = [list(part.coords[0]), list(part.coords[-1])]
                derived.append((fi, pts, part.length))
    for fi, pts, ln in derived:
        add("parapet", pts, ln, [fi], "unlabelled outline piece, geometric length")

    # hole outlines
    for etype, pts, ln, fac in hole_edges:
        add(etype, pts, ln, fac, "opening outline")

    for e in edges:
        e["_derived"] = e["_note"]

    # ---- totals ------------------------------------------------------------
    pitched = sum(f["area_sqft"] for f in facets if f["kind"] == "sloped")
    totals = {
        "total_area_sqft": float(at["total_roof_area"]),
        "pitched_area_sqft": float(at["pitched"]),
        "flat_area_sqft": float(at["flat"]),
        "predominant_pitch_rise": 0.0,
        "predominant_pitch_area_sqft": float(at["predominant_pitch_area"]),
        "squares": at["total_roof_area"] / 100.0,
        "lengths_ft": OrderedDict((t, PRINTED[t]) for t in TYPES),
    }

    notes = [
        "Digitised by hand from photographs of the printed Roofr pages (length report page 3, area report page 4). The plan is a reconstruction accurate to about 3 to 5 percent and is not orthogonalised; edge lengths use the printed label where one exists.",
        "Totals are the PRINTED Roofr numbers and are not recomputed from facets or edges. Per-type edge sums differ from them (see the README table); facet areas sum to 5410 against the printed 5405 because labels appear rounded up.",
        "plan_area_sqft is the area of the reconstructed polygon minus the openings it contains. area_sqft is the PRINTED Roofr facet area (already net of openings). They differ by up to 10 percent (Flat 922 includes an unlabelled lobe, polygon 1020 vs printed 922) because of photo distortion, so area_sqft is not plan_area_sqft times the slope factor.",
        "Hip pitch is not printed. Research derived about 5/12 (plausible 4.5 to 6.5) from hip lengths and areas; this fixture uses 3.9/12 from a LiDAR plane fit. The facet areas 300/169/190/289 are the printed truth either way.",
        "Hip west eave split 13 + 12 is uncertain (60 percent) and a short hidden piece may exist; hip bottom-west label 12 measures 10 to 11 ft in pixels.",
        "Hip edge labels 20, 20, 20, 18 (rounded up) sum to 78 ft against the printed hip total 76 ft 2 in. Ridge 7 ft 9 in is the printed total placed on the single reconstructed ridge segment.",
        "Which vertical teal edge carries which label 11 is uncertain (80 percent); label 22 beside the divider junction is not an extra eave; label 31 on the divider is overprinted by a dashed rectangle.",
        "Awnings are sloped, pitch unknown (areas 82/87/86 vs plan 81 give 0 to 4/12); treated as shed blocks at 3.9/12, aspect 180, with a parapet top. Their positions are from the photo. Only four yellow rake runs of about 6 ft were seen against 32 ft printed; this fixture places four runs of 7.5 ft on the lower, free part of the awning sides (30 ft), so the split between rake and parapet on those sides is a guess.",
        "Parapet 423.8 ft printed: labelled edges and awning tops cover most of it; the rest are short unlabelled outline pieces taken at geometric length from the reconstruction. Step flashing 50 ft (brown dots) may be drawn over some orange edges.",
        "The 17 dashed openings are stored as holes of kind chimney (curb) so that their outlines carry wall_flashing (16) and step_flashing (1) edges. The photo only shows blue dashes, so skylight vs curb is not known. Their perimeters sum to about 244 ft; the printed wall flashing is 344 ft 5 in and the missing 100 ft is not visible in the drawing (UNRESOLVED).",
        "Opening count is 17 plus or minus 1 (overprinted labels at two places).",
        "Roofr marks flat-to-flat internal lines as eaves (about 65 ft); they are included as eave edges. Flat-to-flat boundaries that are not drawn as a coloured edge are omitted.",
        "Every polygon is clean and closed but facet polygons do not tile their neighbours exactly (photo distortion), so small gaps and overlaps of 1 to 2 ft exist between flats.",
    ]
    warnings = [
        "Wall flashing 344 ft 5 in is only partly located: the opening outlines give about 232 ft; the other ~100 ft (flat roofs meeting higher walls) is not visible in the drawing and has no edges here.",
        "Step flashing 50 ft is only partly located: one outlined opening (about 12 ft) is drawn.",
        "Two-story and two-layer areas are 0 in the report and were not measured; unspecified-pitch area is 0.",
        "Roof material (Tile on the hip and awnings, Tear off on the flats, Re stack) is handwritten on the report and is not in the model.",
        "Parapet height and wall heights are unknown; eave_height_ft is null on every block.",
        "Printed totals are authoritative; summing this fixture's edges or facets will not reproduce them exactly, so a totals-recompute test must use the tolerances in the README.",
    ]

    model = OrderedDict()
    model["schema"] = "bond.roof_model/0.1"
    model["generated_at"] = "2026-11-07T21:00:00Z"
    model["address"] = {"line1": "100 Example Ave", "city": "Sampletown",
                        "state": "CA", "zip": "90000",
                        "formatted": "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000"}  # real site: local/sites.json
    model["origin"] = {"lat": 0.0, "lng": 0.0}
    model["north_deg"] = 0
    model["units"] = "ft"
    model["source"] = {"method": "manual", "footprint": None, "lidar": None,
                       "solar": None}
    model["blocks"] = blocks
    model["facets"] = facets
    model["edges"] = [{k: v for k, v in e.items() if not k.startswith("_")}
                      for e in edges]
    model["holes"] = [{k: v for k, v in h.items() if not k.startswith("_")}
                      for h in holes]
    model["totals"] = totals
    model["confidence"] = {"overall": "medium", "notes": notes}
    model["warnings"] = warnings
    model["debug"] = {
        "edge_origin": {e["id"]: e["_derived"] for e in edges},
        "hole_source_ids": {h["id"]: h["_src"] for h in holes},
        "facet_source_ids": {v: k for k, v in fid.items()},
    }

    with open(args.out, "w") as fh:
        json.dump(model, fh, indent=1)
        fh.write("\n")
    ok = check(model, args.out)
    sys.exit(0 if ok else 1)


def check(m, path):
    ok = True

    def bad(msg):
        nonlocal ok
        ok = False
        print("FAIL:", msg)

    L = m["totals"]["lengths_ft"]
    if sorted(L) != sorted(TYPES):
        bad("lengths_ft keys %s" % sorted(L))
    sums = {t: 0.0 for t in TYPES}
    for e in m["edges"]:
        if len(e["points"]) != 2:
            bad("edge %s not two points" % e["id"])
        if not e["length_ft"] > 0:
            bad("edge %s length <= 0" % e["id"])
        if e["type"] not in sums:
            bad("edge %s type %s" % (e["id"], e["type"]))
        else:
            sums[e["type"]] += e["length_ft"]
        if not 1 <= len(e["facets"]) <= 2:
            bad("edge %s facets %s" % (e["id"], e["facets"]))
    print("%-14s %9s %9s %8s %7s" % ("type", "edges_sum", "printed", "diff", "pct"))
    for t in TYPES:
        pr = L[t]
        df = sums[t] - pr
        pct = (100.0 * df / pr) if pr else 0.0
        strict = t in ("eave", "hip", "ridge", "rake", "parapet")
        flag = ""
        if strict and abs(pct) > 10:
            flag = "  FAIL >10%"
            bad("%s off by %.1f%%" % (t, pct))
        elif not strict and pr and abs(pct) > 10:
            flag = "  (partly located, expected)"
        print("%-14s %9.2f %9.2f %+8.2f %+6.1f%%%s" % (t, sums[t], pr, df, pct, flag))
    area = sum(f["area_sqft"] for f in m["facets"])
    print("facet area_sqft sum %.1f vs printed 5405 (tolerance 10)" % area)
    if abs(area - 5405) > 10:
        bad("facet area sum %.1f" % area)
    for kind, items in [("facet", m["facets"]), ("block", m["blocks"]),
                        ("hole", m["holes"])]:
        for it in items:
            pg = Polygon(it["polygon"])
            if not pg.is_valid or pg.area <= 0:
                bad("%s %s polygon invalid" % (kind, it["id"]))
            if kind != "hole" and it.get("plan_area_sqft", 1) <= 0:
                bad("%s %s plan area" % (kind, it["id"]))
    ids = {f["id"] for f in m["facets"]}
    for e in m["edges"]:
        if not set(e["facets"]) <= ids:
            bad("edge %s unknown facet" % e["id"])
    for f in m["facets"]:
        if f["block"] not in {b["id"] for b in m["blocks"]}:
            bad("facet %s block" % f["id"])
    if abs(m["totals"]["squares"] - m["totals"]["total_area_sqft"] / 100) > 1e-9:
        bad("squares")
    if m["source"]["method"] != "manual":
        bad("source.method")
    print("edges %d, facets %d, blocks %d, holes %d; file %d bytes" % (
        len(m["edges"]), len(m["facets"]), len(m["blocks"]), len(m["holes"]),
        os.path.getsize(path)))
    print("CHECK", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    main()
