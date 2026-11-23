"""Turn a hand label (vertices + facet rings) into CONTRACT-2 truth and an overlay picture.

label = {"vertices": {"a":[x,y],...}, "facets":[{"id":"f1","ring":["a","b",...]}],
         "edge_types": {"a-b":"step"}  (optional overrides), "confidence": "...", "notes": "...", "not_roof": "..."}
Edge typing is a plain geometric rule applied to the labeller's own polygons and the planes measured inside them.
"""

from __future__ import annotations

import math

import numpy as np
from shapely import contains_xy
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from . import viz as rv
from .viz import plt

TYPES = ("eave", "rake", "ridge", "hip", "valley", "step", "flat_edge", "transition")
ECOL = {
    "eave": "#1a9850",
    "rake": "#ff7f00",
    "ridge": "#e41a1c",
    "hip": "#984ea3",
    "valley": "#1f78b4",
    "step": "#000000",
    "flat_edge": "#00ced1",
    "transition": "#a65628",
}


def _z(pl, x, y):
    return pl[0] * x + pl[1] * y + pl[2]


def build(h: rv.House, label: dict, source="llm_vision", provenance=""):
    V = {k: tuple(map(float, v)) for k, v in label["vertices"].items()}
    facets, polys = [], {}
    for f in label["facets"]:
        ring = [V[k] for k in f["ring"]]
        poly = Polygon(ring)
        fit = h.fit_plane(ring)
        polys[f["id"]] = poly
        d = {
            "id": f["id"],
            "ring": f["ring"],
            "polygon": [[round(x, 2), round(y, 2)] for x, y in ring],
            "valid": bool(poly.is_valid),
        }
        d.update(
            {
                k: fit.get(k)
                for k in (
                    "plane",
                    "pitch_rise",
                    "aspect_deg",
                    "roof_type",
                    "plan_area_sqft",
                    "area_sqft",
                    "points",
                    "rms_m",
                    "inlier_fraction",
                    "above_plane_fraction",
                    "below_plane_fraction",
                    "mean_height_above_ground_m",
                )
            }
        )
        if f.get("roof_type"):
            d["roof_type"] = f["roof_type"]
        if f.get("note"):
            d["note"] = f["note"]
        if d["plane"] is None:  # too few returns: keep the plan area, pitch unknown
            d["area_sqft"] = None
        facets.append(d)
    F = {f["id"]: f for f in facets}
    # ---- edges from shared vertex pairs
    use = {}
    for f in label["facets"]:
        r = f["ring"]
        for i in range(len(r)):
            a, b = r[i], r[(i + 1) % len(r)]
            if a == b:
                continue
            use.setdefault(tuple(sorted((a, b))), []).append(f["id"])
    ov = {tuple(sorted(k.split("-"))): v for k, v in (label.get("edge_types") or {}).items()}
    edges = []
    for (a, b), fs in use.items():
        (xa, ya), (xb, yb) = V[a], V[b]
        L2 = math.hypot(xb - xa, yb - ya)
        if L2 < 1e-6:
            continue
        pls = [F[i]["plane"] for i in fs if F[i]["plane"]]
        if pls:
            za = float(np.mean([_z(p, xa, ya) for p in pls]))
            zb = float(np.mean([_z(p, xb, yb) for p in pls]))
        else:
            za = zb = float("nan")
        run_slope = abs(zb - za) / L2 if pls else 0.0
        t = None
        if len(fs) == 1:
            f = F[fs[0]]
            if f["roof_type"] == "flat":
                t = "flat_edge"
            else:
                # eave if the edge runs across the slope (level) at the LOW side; level at the high side is still reported as eave-type "rake"? -> call it rake only when it climbs
                t = "eave" if run_slope < 0.5 * (f["pitch_rise"] or 0) / 12.0 else "rake"
        else:
            f1, f2 = F[fs[0]], F[fs[1]]
            if f1["plane"] and f2["plane"]:
                mx, my = (xa + xb) / 2, (ya + yb) / 2
                gap = abs(_z(f1["plane"], mx, my) - _z(f2["plane"], mx, my))
                nx_, ny_ = -(yb - ya) / L2, (xb - xa) / L2

                def inside_pt(poly, mx=mx, my=my, nx_=nx_, ny_=ny_):
                    for d in (0.35, 0.15, 0.05):
                        for sg in (1, -1):
                            q = Point(mx + sg * d * nx_, my + sg * d * ny_)
                            if poly.contains(q):
                                return q
                    return poly.representative_point()

                c1 = inside_pt(polys[fs[0]])
                c2 = inside_pt(polys[fs[1]])
                # convex (ridge/hip) if each facet's own plane is LOWER than the other plane just inside it
                conv = (_z(f1["plane"], c1.x, c1.y) < _z(f2["plane"], c1.x, c1.y)) and (
                    _z(f2["plane"], c2.x, c2.y) < _z(f1["plane"], c2.x, c2.y)
                )
                conc = (_z(f1["plane"], c1.x, c1.y) > _z(f2["plane"], c1.x, c1.y)) and (
                    _z(f2["plane"], c2.x, c2.y) > _z(f1["plane"], c2.x, c2.y)
                )
                if gap > 0.35:
                    t = "step"
                elif f1["roof_type"] != f2["roof_type"]:
                    t = "transition"
                elif conv:
                    t = "ridge" if run_slope < 0.06 else "hip"
                elif conc:
                    t = "valley"
                else:
                    t = "ridge" if run_slope < 0.06 else "hip"
            else:
                t = "step"
        t = ov.get((a, b), t)
        L3 = math.hypot(L2, (zb - za)) if pls and not math.isnan(za) else L2
        edges.append(
            {
                "type": t,
                "v": [a, b],
                "p0": [round(xa, 2), round(ya, 2), None if math.isnan(za) else round(za, 2)],
                "p1": [round(xb, 2), round(yb, 2), None if math.isnan(zb) else round(zb, 2)],
                "length_ft": round(L3 * rv.M2FT, 1),
                "facets": fs,
            }
        )
    lengths = {t: round(sum(e["length_ft"] for e in edges if e["type"] == t), 1) for t in TYPES}
    okf = [f for f in facets if f["area_sqft"]]
    area = sum(f["area_sqft"] for f in okf)
    flat = sum(f["area_sqft"] for f in okf if f["roof_type"] == "flat")
    pit = [f for f in okf if f["roof_type"] == "pitched"]
    pred = None
    if pit:
        bins = {}
        for f in pit:
            bins[round(f["pitch_rise"])] = bins.get(round(f["pitch_rise"]), 0) + f["area_sqft"]
        pred = max(bins, key=bins.get)
    outline = unary_union([p.buffer(0) for p in polys.values()])
    rings = [
        [[round(c[0], 2), round(c[1], 2)] for c in g.exterior.coords]
        for g in (outline.geoms if hasattr(outline, "geoms") else [outline])
    ]
    truth = {
        "house_id": h.house_id,
        "source": source,
        "confidence": label.get("confidence", "medium"),
        "squares": round(area / 100.0, 2),
        "area_sqft": round(area, 1),
        "flat_area_sqft": round(flat, 1),
        "pitched_area_sqft": round(area - flat, 1),
        "predominant_pitch": pred,
        "facet_count": len(facets),
        "lengths_ft": {k: lengths[k] for k in ("eave", "rake", "ridge", "hip", "valley", "step")},
        "lengths_ft_extra": {k: lengths[k] for k in ("flat_edge", "transition")},
        "facets": [
            {
                k: f[k]
                for k in (
                    "id",
                    "polygon",
                    "plane",
                    "pitch_rise",
                    "aspect_deg",
                    "roof_type",
                    "plan_area_sqft",
                    "area_sqft",
                    "points",
                    "rms_m",
                    "inlier_fraction",
                )
            }
            | ({"note": f["note"]} if f.get("note") else {})
            for f in facets
        ],
        "edges": edges,
        "roof_outline": rings,
        "notes": label.get("notes", ""),
        "could_not_see": label.get("could_not_see", ""),
        "provenance": provenance,
    }
    return truth, facets, edges, polys


def coverage(h: rv.House, facets, polys):
    """How well the label explains the LiDAR: roof returns near the building that fall in no facet, and returns far from their facet's plane."""
    U = unary_union([p.buffer(0) for p in polys.values()])
    zone = U.buffer(1.0).union(h.fp.buffer(0.5))
    p = h.ng[h.ng_hag > 1.8]
    inz = contains_xy(zone, p[:, 0], p[:, 1])
    p = p[inz]
    res = np.full(len(p), np.nan)
    for f in facets:
        if not f["plane"]:
            continue
        m = contains_xy(polys[f["id"]], p[:, 0], p[:, 1])
        res[m] = p[m, 2] - _z(f["plane"], p[m, 0], p[m, 1])
    return p, res


def overlay(h: rv.House, truth, facets, edges, polys, path, title=""):
    r = h.rasters()
    ext = (h.bbox[0], h.bbox[2], h.bbox[1], h.bbox[3])
    p, res = coverage(h, facets, polys)
    panels = [
        ("aspect", "label over ASPECT map"),
        (
            "resid",
            "CHECK: LiDAR returns vs label (grey = fits its facet within 12 cm, red = above plane, blue = below, yellow = roof-height return in NO facet)",
        ),
    ]
    paths = []
    for key, ttl in panels:
        fig, ax = rv._axes(h, f"{title} {ttl}")
        if key == "aspect":
            ax.imshow(
                rv.aspect_rgb(r["aspect"], r["slope"], r["hag"]),
                origin="lower",
                extent=ext,
                interpolation="nearest",
                alpha=0.85,
            )
        else:
            ax.set_facecolor("#f4f4f4")
            un = np.isnan(res)
            ax.scatter(
                p[~un, 0],
                p[~un, 1],
                s=5,
                c=np.where(np.abs(res[~un]) < 0.12, 0.0, np.sign(res[~un])),
                cmap="coolwarm",
                vmin=-1.6,
                vmax=1.6,
                linewidths=0,
            )
            ok = np.abs(res) < 0.12
            ax.scatter(p[ok, 0], p[ok, 1], s=4, c="#bbbbbb", linewidths=0)
            ax.scatter(p[un, 0], p[un, 1], s=7, c="#e6b800", linewidths=0)
        rv._decor(h, ax, "k", "k")
        for f in facets:
            poly = polys[f["id"]]
            c = poly.representative_point()
            if f["roof_type"] == "flat":
                ax.fill(
                    *poly.exterior.xy, facecolor="none", edgecolor="#00ced1", hatch="///", lw=0, alpha=0.6
                )
            lab = f"{f['id']}\n{f['pitch_rise']}/12" if f["plane"] else f"{f['id']}\n?"
            ax.text(
                c.x,
                c.y,
                lab + ("\nFLAT" if f["roof_type"] == "flat" else ""),
                ha="center",
                va="center",
                fontsize=7.5,
                fontweight="bold",
                color="k",
                bbox={"boxstyle": "round,pad=0.15", "fc": "w", "ec": "none", "alpha": 0.75},
            )
        for e in edges:
            ax.plot(
                [e["p0"][0], e["p1"][0]],
                [e["p0"][1], e["p1"][1]],
                color=ECOL[e["type"]],
                lw=2.6,
                solid_capstyle="round",
            )
        for k, (x, y) in truth["_vertices"].items():
            ax.plot(x, y, "o", ms=3.5, color="k")
            ax.text(
                x + 0.12,
                y + 0.12,
                k,
                fontsize=7,
                color="k",
                bbox={"boxstyle": "round,pad=0.05", "fc": "#ffffcc", "ec": "none", "alpha": 0.8},
            )
        hs = [plt.Line2D([0], [0], color=ECOL[t], lw=3, label=t) for t in rv_types_present(edges)]
        ax.legend(handles=hs, loc="lower right", fontsize=7, framealpha=0.9)
        pth = str(path).replace(".png", f"_{key}.png")
        rv._save(fig, pth)
        paths.append(pth)
    un = np.isnan(res)
    stats = {
        "roof_returns_near_building": len(p),
        "in_no_facet_pct": round(100 * float(un.mean()), 1),
        "in_facet_within_12cm_pct": round(100 * float((np.abs(res[~un]) < 0.12).mean()), 1)
        if (~un).any()
        else None,
    }
    return paths, stats


def rv_types_present(edges):
    return [t for t in TYPES if any(e["type"] == t for e in edges)]
