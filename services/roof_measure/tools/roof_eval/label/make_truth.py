"""make_truth: roof ground truth for EVALUATION ONLY, labelled by a vision model from LiDAR renders.

This module SPENDS MONEY when run() is called with confirm_spend=True. Nothing in the repo calls it by accident: the
entry point (``python -m tools.roof_eval.label run``) refuses without --spend-cap and --confirm-spend. The key comes only
from the environment variable ANTHROPIC_API_KEY (never printed, never read from a file).

house_folder holds points_wide.npy (x, y, z, class) and meta.json (footprint_local_m_wkt). Its directory name is the
house's opaque id. The model sees pictures and measures with local tools (plane fit, plane intersection, profile, height
grid, plane map, roof edge); it never sees the product pipeline's planes or models. Nothing but pictures, numbers in the
local frame and the prompt is sent: no address, no coordinates of the frame origin.
Writes <truth-root>/<id>/truth.llm_vision.<tag>.json (or <out>/truth.llm_vision.api.json), overlay pictures and run.json.
"""

from __future__ import annotations

import base64
import fcntl
import json
import math
import os
import re
import time
from pathlib import Path

import numpy as np

from . import build as lt
from . import viz as rv

MODEL = "claude-fable-5-2"  # the labeller; one model id, no fallbacks in this file other than the API's own
PRICE = {
    "input": 8.0,
    "output": 40.0,
    "cache_read": 0.20,
    "cache_write": 10.0,
}  # USD per million tokens (cache write assumed 1.25 x input)
PROMPT_VERSION = (
    "make_truth/2026-11-22-a"  # prompt unchanged; privacy audit, z datum shift, cost cap, schema r2
)

SYSTEM = """You are an experienced roof estimator producing a measured roof diagram of ONE house from airborne LiDAR. Your result is used as reference truth to evaluate software, so accuracy and honesty about what you could not see matter more than a tidy picture.

FRAME. All coordinates are local METRES: x = east, y = north. Every picture has a 1 m grid with labelled axes, a north arrow and a 5 m scale bar. Heights are metres.

PICTURES (same frame, 0.1 m per pixel):
 (a) height above ground with contours; (b) hillshade; (c) aspect: hue = downslope direction, each roof plane is one flat colour, ridges/hips/valleys are colour boundaries (boundaries are blurred by about 0.5 m); (d) slope in rise per 12 with the 2/12 line; (e) crease map: bright lines are ridges, hips, valleys, steps and roof edges; (f) raw returns coloured by height: shows the true roof edge including overhang; (g) profile cuts; optionally (h)/(i) aerial photos, which are older and coarser than the LiDAR and show roofs displaced by up to 1 m, so use them only to recognise things (tree, patio cover, deck), never for coordinates.
 The dashed county building outline is only a hint: it follows the walls, is often 0.5-1 m smaller than the roof and can be shifted by a metre. The roof edge is where roof-height returns stop.

WHAT TO DELIVER. Vertices (named points) and facets (rings of vertex names). Neighbouring facets MUST share the same vertex names along their common edge, because edges are derived from shared vertex pairs (ridge, hip, valley, step, transition) and unshared ones (eave, rake, flat_edge). If a long edge of one facet touches two facets, put the intermediate vertex in its ring too. Pitch, area and edge lengths are computed for you from the LiDAR returns inside each polygon, so the polygons carry all the information.

RULES OF THE TRADE
 - A facet with pitch below 2/12 is FLAT (different material). Keep flat and pitched areas in separate facets; a low patio cover, porch roof or lower deck is its own facet with a note.
 - Include the overhang: draw eaves and rakes about 0.1 m outside the outermost roof-height returns (the last return sits a little inside the true edge).
 - Do not include trees (noisy aspect, heights above the roof), neighbouring buildings, detached buildings, fences or walls. Small bumps (chimney, vent, rooftop unit) are not facets: mention them in notes.
 - Most houses are rotated a few degrees. Estimate the rotation first (ridge direction or a fitted plane's aspect), then think in building axes: eaves parallel to ridges, rakes perpendicular. Tools that take `theta_deg` work in building axes (u along theta, v 90 degrees counter-clockwise from u).
 - Get lines from measurements, not from colour boundaries: fit planes in clean rectangles well inside each facet, intersect them for ridges/hips/valleys, use plane_map to see which returns belong to which plane, height_grid for flat multi-level roofs and for steps, roof_edge for eaves and rakes. On sloping ground 'height above ground' tilts flat roofs: read absolute heights from height_grid instead.
 - A plane fit over a whole facet with inlier_fraction below about 0.9, or many returns above/below, means the polygon mixes two surfaces: split or move it.
 - Never invent what you cannot see. Say in `could_not_see` what is hidden (under trees, too few returns, ambiguous deck/roof) and set confidence honestly (high / medium / low).

PROCESS. Work in a small number of rich tool calls (several tools can be called in one turn). When you have a complete draft, call submit_label. The first submission is returned to you drawn over the aspect map and as a LiDAR residual check (grey = return fits its facet within 12 cm, red = above, blue = below, yellow = roof-height return in no facet) with per-facet statistics; look at it, correct what is off, and submit once more: the second submission is final. You have a limited number of turns; the user message says how many."""

POLY = {
    "type": "array",
    "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    "minItems": 3,
    "description": "polygon as [[x,y],...] in local metres",
}
PT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
LABEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["vertices", "facets", "confidence", "notes", "could_not_see"],
    "properties": {
        "vertices": {
            "type": "object",
            "description": "name -> [x, y] in local metres",
            "additionalProperties": PT,
        },
        "facets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "ring"],
                "properties": {
                    "id": {"type": "string"},
                    "ring": {"type": "array", "items": {"type": "string"}, "minItems": 3},
                    "note": {"type": "string"},
                },
            },
        },
        "edge_types": {
            "type": "object",
            "description": "optional overrides of the derived edge type, key 'v1-v2', value one of eave, rake, ridge, hip, valley, step, flat_edge, transition",
            "additionalProperties": {"type": "string", "enum": list(lt.TYPES)},
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
        "could_not_see": {"type": "string"},
    },
}
TOOLS = [
    {
        "name": "fit_plane",
        "description": "Robust plane through the LiDAR returns inside a polygon: pitch (rise per 12), aspect (downslope, 0=N 90=E), plane z=a*x+b*y+c, rms, inlier fraction, fractions of returns above/below, plan and sloped area. Use clean rectangles well inside a facet to measure it.",
        "input_schema": {
            "type": "object",
            "required": ["name", "polygon"],
            "additionalProperties": False,
            "properties": {"name": {"type": "string"}, "polygon": POLY},
        },
    },
    {
        "name": "intersect_planes",
        "description": "Line where the planes fitted in two polygons meet (a ridge, hip or valley candidate), as two end points [x,y,z] clipped to the polygons' surroundings, with the slope along the line (about 0 = ridge).",
        "input_schema": {
            "type": "object",
            "required": ["polygon_a", "polygon_b"],
            "additionalProperties": False,
            "properties": {"polygon_a": POLY, "polygon_b": POLY},
        },
    },
    {
        "name": "profile",
        "description": "Top-surface height above ground every `step` metres along a line from p0 to p1 (0.8 m wide strip). Shows eaves, ridges, steps, flat parts.",
        "input_schema": {
            "type": "object",
            "required": ["p0", "p1"],
            "additionalProperties": False,
            "properties": {"p0": PT, "p1": PT, "step": {"type": "number"}},
        },
    },
    {
        "name": "height_grid",
        "description": "Text grid of the highest return per cell (absolute height in decimetres above a base) over a box given in building axes (u,v) rotated by theta_deg; rows north to south. Best tool for flat multi-level roofs, steps, exact eave lines and for following a valley row by row. Max 70 x 70 cells.",
        "input_schema": {
            "type": "object",
            "required": ["u0", "v0", "u1", "v1"],
            "additionalProperties": False,
            "properties": {
                "u0": {"type": "number"},
                "v0": {"type": "number"},
                "u1": {"type": "number"},
                "v1": {"type": "number"},
                "cell": {"type": "number"},
                "theta_deg": {"type": "number"},
            },
        },
    },
    {
        "name": "plane_map",
        "description": "Fit a plane in each named clean polygon, then print a character map (first letter of the name) of which plane every roof return lies on (within 8 cm); '?' = on two planes at once (their intersection), '.' = on none. Shows facet extents, valleys and hips directly. Names must start with different letters. Box in x,y. Max 70 x 70 cells.",
        "input_schema": {
            "type": "object",
            "required": ["planes", "x0", "y0", "x1", "y1"],
            "additionalProperties": False,
            "properties": {
                "planes": {"type": "object", "additionalProperties": POLY},
                "x0": {"type": "number"},
                "y0": {"type": "number"},
                "x1": {"type": "number"},
                "y1": {"type": "number"},
                "cell": {"type": "number"},
            },
        },
    },
    {
        "name": "roof_edge",
        "description": "For each ray [p_on_roof, p_outside] (x,y), walk outward and return the last roof-height return before a gap: the roof edge on that ray (accurate to about 0.3 m; trees or a neighbour touching the roof make the ray run on, visible as a jump in height).",
        "input_schema": {
            "type": "object",
            "required": ["rays"],
            "additionalProperties": False,
            "properties": {
                "rays": {
                    "type": "array",
                    "items": {"type": "array", "items": PT, "minItems": 2, "maxItems": 2},
                }
            },
        },
    },
    {
        "name": "submit_label",
        "description": "Submit the roof label. First call: you get it back drawn and checked. Second call: final.",
        "input_schema": LABEL_SCHEMA,
    },
]


# ----------------------------------------------------------------------------- local tools
def t_height_grid(h, u0, v0, u1, v1, cell=0.5, theta_deg=0.0):
    cell = max(cell, (u1 - u0) / 70, (v1 - v0) / 70, 0.2)
    th = math.radians(theta_deg)
    c, s = math.cos(th), math.sin(th)
    w = h.w
    u = w[:, 0] * c + w[:, 1] * s
    v = -w[:, 0] * s + w[:, 1] * c
    m = (u >= u0) & (u < u1) & (v >= v0) & (v < v1)
    if m.sum() == 0:
        return "no returns in that box"
    u, v, z = u[m], v[m], w[m, 2]
    base = math.floor(np.percentile(z, 1))
    nx, ny = max(1, round((u1 - u0) / cell)), max(1, round((v1 - v0) / cell))
    g = np.full((ny, nx), -1.0)
    np.maximum.at(
        g,
        (
            np.minimum(ny - 1, ((v - v0) / cell).astype(int)),
            np.minimum(nx - 1, ((u - u0) / cell).astype(int)),
        ),
        z - base,
    )
    out = [
        f"cell {cell:.2f} m; value = highest return in the cell, decimetres above z={base} m; '.' = no return; theta={theta_deg}; x = u*cos - v*sin, y = u*sin + v*cos",
        "   v\\u " + " ".join(f"{u0 + (k + 0.5) * cell:4.1f}" for k in range(nx)),
    ]
    for r in range(ny - 1, -1, -1):
        out.append(
            f"{v0 + (r + 0.5) * cell:6.2f} "
            + " ".join("   ." if g[r, k] < 0 else f"{round(g[r, k] * 10):4d}" for k in range(nx))
        )
    return "\n".join(out)


def t_plane_map(h, planes, x0, y0, x1, y1, cell=0.33):
    cell = max(cell, (x1 - x0) / 70, (y1 - y0) / 70, 0.2)
    names = list(planes)
    fits = [h.fit_plane(planes[n]) for n in names]
    ok_names = [n for n, f in zip(names, fits) if f.get("plane")]
    if not ok_names:
        return "no plane could be fitted"
    pls = [f["plane"] for f in fits if f.get("plane")]
    p = h.ng[h.ng_hag > 1.5]
    p = p[(p[:, 0] >= x0) & (p[:, 0] < x1) & (p[:, 1] >= y0) & (p[:, 1] < y1)]
    if len(p) == 0:
        return "no roof-height returns in that box"
    R = np.abs(np.stack([p[:, 2] - (a * p[:, 0] + b * p[:, 1] + c) for a, b, c in pls], 1))
    best = R.argmin(1)
    ok = R.min(1) < 0.08
    amb = (np.sort(R, 1)[:, 1] < 0.08) if len(pls) > 1 else np.zeros(len(p), bool)
    nx, ny = max(1, round((x1 - x0) / cell)), max(1, round((y1 - y0) / cell))
    g = [[" "] * nx for _ in range(ny)]
    for (x, y), b, o, a in zip(p[:, :2], best, ok, amb):
        g[min(ny - 1, int((y - y0) / cell))][min(nx - 1, int((x - x0) / cell))] = (
            "?" if a else (ok_names[b][0] if o else ".")
        )
    out = [
        "fits: "
        + json.dumps(
            {
                n: {k: f.get(k) for k in ("pitch_rise", "aspect_deg", "rms_m", "points", "plane")}
                for n, f in zip(names, fits)
            }
        ),
        f"cell {cell:.2f} m; rows north to south; first column = y of the row; last line = x of every 3rd column",
    ]
    for r in range(ny - 1, -1, -1):
        out.append(f"{y0 + (r + 0.5) * cell:6.2f} " + "".join(g[r]))
    out.append("       " + "".join(f"{x0 + (k + 0.5) * cell:<3.0f}" if k % 3 == 0 else "" for k in range(nx)))
    return "\n".join(out)


def t_roof_edge(h, rays):
    res = []
    for p_in, p_out in rays:
        t, z, _cls, L = h.profile(p_in, p_out, 0.5)
        g = float(h.ground_z([p_in[0]], [p_in[1]])[0])
        o = np.argsort(t)
        t, z = t[o], z[o]
        hi = z - g > 1.8
        if not hi.any():
            res.append({"ray": [p_in, p_out], "edge": None})
            continue
        th = t[hi]
        last = th[0]
        for v in th[1:]:
            if v - last > 0.6:
                break
            last = v
        d = (np.array(p_out) - np.array(p_in)) / L
        q = np.array(p_in) + d * last
        res.append(
            {
                "ray": [p_in, p_out],
                "edge_xy": [round(float(q[0]), 2), round(float(q[1]), 2)],
                "distance_m": round(float(last), 2),
                "height_above_ground_there_m": round(float(np.median(z[hi][np.abs(th - last) < 0.5]) - g), 2),
                "ran_to_end_of_ray": bool(last > L - 0.3),
            }
        )
    return json.dumps(res)


def img_block(path):
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(Path(path).read_bytes()).decode(),
        },
    }


def forbidden_tokens(h):
    """Strings that must never appear in anything sent: the house id, address parts, zip, coordinates, frame origin, parcel / outline ids."""
    m = h.meta
    toks = {h.house_id.lower(), h.house_id.lower().replace("_", " ")}
    addr = str(m.get("address") or "").lower()
    if addr:
        toks.add(addr)
        parts = [x.strip() for x in addr.split(",")]
        toks.add(parts[0])  # house number and street
        street = re.sub(r"^\S+\s+", "", parts[0])
        if len(street) >= 6:
            toks.add(street)
        for x in parts[1:]:
            x = re.sub(r"\b[a-z]{2}\b\s*\d{5}.*$", "", x).strip()
            if len(x) >= 5:
                toks.add(x)  # city
        toks |= set(re.findall(r"\b\d{5}\b", addr))  # zip

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("lat", "lng", "lon", "latitude", "longitude") and isinstance(v, (int, float)):
                    toks.add(f"{abs(v):.3f}")
                elif k in ("formatted",) and isinstance(v, str):
                    toks.add(v.lower())
                else:
                    walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(m)
    for k in ("frame_x0_m", "frame_y0_m"):
        if m.get(k) is not None:
            toks.add(str(int(m[k])))
    for fn in ("footprint.geojson", "parcel.geojson"):
        f = h.folder / fn
        if f.exists():
            try:
                for ft in json.loads(f.read_text()).get("features", []):
                    pr = ft.get("properties") or {}
                    for k in ("parcel_id", "ain", "AIN", "APN", "apn", "id"):
                        v = pr.get(k)
                        if v is not None and len(str(v)) >= 6:
                            toks.add(str(v).lower())
            except (OSError, ValueError, AttributeError):
                pass  # an unreadable sidecar adds no tokens; the id, address and frame tokens still apply
    return {t for t in toks if t and len(t) >= 5}


def text_of(obj):
    """All text that a payload fragment carries (image bytes excluded: checked separately, they are rendered locally with fixed titles)."""
    out = []

    def walk(o):
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            if o.get("type") == "image":
                return
            for k, v in o.items():
                out.append(str(k))
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
        elif hasattr(o, "model_dump"):
            walk(o.model_dump())
        elif o is not None:
            out.append(str(o))

    walk(obj)
    return "\n".join(out).lower()


def audit(obj, toks, where):
    t = text_of(obj)
    hits = sorted(x for x in toks if x in t)
    if hits:
        raise SystemExit(
            f"PRIVACY AUDIT FAILED in {where}: {len(hits)} forbidden token(s) present; nothing sent"
        )
    return len(t)


def png_text_chunks(path):
    """names of textual chunks inside a PNG (tEXt/iTXt/zTXt) with their values, to prove no path or address rides in image metadata"""
    import struct

    b = Path(path).read_bytes()
    i = 8
    out = []
    while i < len(b):
        n, typ = struct.unpack(">I4s", b[i : i + 8])
        if typ in (b"tEXt", b"iTXt", b"zTXt"):
            out.append(b[i + 8 : i + 8 + n][:200].decode("latin1"))
        i += 12 + n
    return out


def finalize(truth, z0, tag):
    """schema r2: level_change instead of step; borderline flag near 2/12; absolute z restored (the model worked in a shifted datum)."""
    L = truth["lengths_ft"]
    L["level_change"] = L.pop("step")
    for e in truth["edges"]:
        if e["type"] == "step":
            e["type"] = "level_change"
        for k in ("p0", "p1"):
            if e[k][2] is not None:
                e[k][2] = round(e[k][2] + z0, 2)
    for f in truth["facets"]:
        if f.get("plane"):
            f["plane"] = [f["plane"][0], f["plane"][1], round(f["plane"][2] + z0, 4)]
        pr = f.get("pitch_rise")
        f["roof_type_rule"] = "flat when fitted pitch < 2.0/12"
        f["borderline"] = bool(pr is not None and 1.5 <= pr <= 2.5)
    truth["schema"] = (
        "truth.llm_vision/r2 (lengths_ft.level_change; facet.borderline for 1.5-2.5/12; roof_type split at 2.0/12)"
    )
    truth["borderline_area_sqft"] = round(
        sum((f.get("area_sqft") or 0) for f in truth["facets"] if f["borderline"]), 1
    )
    truth["run_tag"] = tag
    return truth


def log_spend(path, house_id, tag, usage, cost, stop):
    if not path:
        return
    with open(path, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        if fh.tell() == 0:
            fh.write(
                "utc\thouse_id\ttag\tinput_tokens\toutput_tokens\tcache_read_tokens\tcache_write_tokens\tusd_estimate\tstop\n"
            )
        fh.write(
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t{house_id}\t{tag}\t{usage['input']}\t{usage['output']}\t{usage['cache_read']}\t{usage['cache_write']}\t{cost:.3f}\t{stop}\n"
        )


def cost_of(u):
    return (
        u["input"] * PRICE["input"]
        + u["output"] * PRICE["output"]
        + u["cache_read"] * PRICE["cache_read"]
        + u["cache_write"] * PRICE["cache_write"]
    ) / 1e6


# ----------------------------------------------------------------------------- main loop
def run(
    folder,
    out,
    truth_root=None,
    max_turns=40,
    effort="high",
    render_only=False,
    tag="r1",
    max_cost=5.5,
    spend=None,
    dump_request=False,
    confirm_spend=False,
):
    h = rv.House(folder)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pics = rv.render_all(h, out)
    if render_only:
        print(json.dumps(pics, indent=1))
        return None
    toks = forbidden_tokens(h)
    order = [
        k for k in ("height", "aspect", "slope", "crease", "hillshade", "returns", "profiles") if k in pics
    ]
    bx = h.bbox
    content = []
    for k in order:
        content += [{"type": "text", "text": f"Picture: {k}"}, img_block(pics[k])]
    prof = "; ".join(
        f"{n}: ({a[0]:.1f},{a[1]:.1f}) to ({b[0]:.1f},{b[1]:.1f})" for n, a, b in h.profiles_used
    )
    content.append(
        {
            "type": "text",
            "text": f"Label the roof of the main building: the one under the dashed outline. The pictures cover x {bx[0]}..{bx[2]} m, y {bx[1]}..{bx[3]} m. "
            f"LiDAR density about {len(h.w) / ((bx[2] - bx[0]) * (bx[3] - bx[1])):.0f} returns per m2 (all returns). Profile cuts in picture (g): {prof}. "
            f"The county outline vertices are: {[[round(x, 1), round(y, 1)] for x, y in h.fp.exterior.coords]}. "
            f"You have at most {max_turns} turns (one turn = one reply of yours, which may hold several tool calls); plan to submit your first label by turn {max(6, max_turns // 2)}.",
        }
    )
    messages = [{"role": "user", "content": content}]
    n_chars = audit({"system": SYSTEM, "tools": TOOLS, "messages": messages}, toks, "first request")
    meta_chunks = {k: png_text_chunks(pics[k]) for k in order}
    for k, ch in meta_chunks.items():
        audit(ch, toks, f"png metadata {k}")
    (out / "request_audit.json").write_text(
        json.dumps(
            {
                "forbidden_tokens_checked": len(toks),
                "text_chars_first_request": n_chars,
                "images": order,
                "png_text_chunks": meta_chunks,
                "z_datum_shift_applied": True,
                "first_user_text": [b["text"] for b in content if b["type"] == "text"],
            },
            indent=1,
        )
    )
    if dump_request:
        print(
            json.dumps(
                {
                    "system": SYSTEM,
                    "tools": TOOLS,
                    "first_user_text": [b["text"] for b in content if b["type"] == "text"],
                },
                indent=1,
            )
        )
        return None
    if not confirm_spend:
        raise SystemExit(
            "refusing to call the API: run() needs confirm_spend=True (the CLI needs --spend-cap and --confirm-spend)"
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set in the environment")
    import anthropic

    client = anthropic.Anthropic(timeout=900.0)  # key from ANTHROPIC_API_KEY
    transcript = []
    models = set()
    errs = 0
    warned = False
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    turns = 0
    submits = 0
    label = None
    log = []
    stop = "max_turns"
    t0 = time.time()
    while turns < max_turns:
        turns += 1
        try:
            resp = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
                output_config={"effort": effort},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError:
            errs += 1
            print("rate limited; backing off", flush=True)
            if errs > 12:
                stop = "rate_limited"
                break
            time.sleep(min(300, 30 * errs))
            turns -= 1
            continue
        except anthropic.APIStatusError as e:
            errs += 1
            log.append({"turn": turns, "error": f"status {e.status_code}"})
            if e.status_code >= 500 and errs <= 6:
                time.sleep(20 * errs)
                turns -= 1
                continue
            stop = "usage_limit" if "usage limits" in str(e) else f"api_error_{e.status_code}"
            print("api error", e.status_code, str(e)[:300], flush=True)
            break
        except anthropic.APIConnectionError:
            errs += 1
            log.append({"turn": turns, "error": "connection"})
            if errs <= 6:
                time.sleep(20 * errs)
                turns -= 1
                continue
            stop = "connection_error"
            break
        models.add(resp.model)
        u = resp.usage
        usage["input"] += u.input_tokens or 0
        usage["output"] += u.output_tokens or 0
        usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        messages.append({"role": "assistant", "content": resp.content})  # unchanged, incl. thinking blocks
        if resp.stop_reason == "refusal":
            stop = "refusal"
            break
        calls = [b for b in resp.content if b.type == "tool_use"]
        transcript.append(
            {
                "turn": turns,
                "text": [b.text for b in resp.content if b.type == "text"],
                "calls": [{"name": c.name, "input": c.input} for c in calls],
            }
        )
        log.append(
            {
                "turn": turns,
                "stop_reason": resp.stop_reason,
                "model": resp.model,
                "tools": [c.name for c in calls],
                "cost_so_far": round(cost_of(usage), 3),
            }
        )
        print(f"turn {turns}: {resp.stop_reason} {[c.name for c in calls]} ${cost_of(usage):.2f}", flush=True)
        if resp.stop_reason == "max_tokens" and not calls:
            messages.append(
                {"role": "user", "content": "Your reply was cut off. Continue with smaller steps."}
            )
            continue
        if not calls:
            if label is not None:
                stop = "end_turn_after_submit"
                break
            messages.append(
                {"role": "user", "content": "Please continue with the tools and finish with submit_label."}
            )
            continue
        results = []
        final = False
        for c in calls:
            a = c.input
            try:
                if c.name == "fit_plane":
                    r = json.dumps({a["name"]: h.fit_plane(a["polygon"])})
                elif c.name == "intersect_planes":
                    r = json.dumps(h.intersect_planes(a["polygon_a"], a["polygon_b"]))
                elif c.name == "profile":
                    r = json.dumps(h.profile_table(a["p0"], a["p1"], a.get("step", 0.5)))
                elif c.name == "height_grid":
                    r = t_height_grid(
                        h, a["u0"], a["v0"], a["u1"], a["v1"], a.get("cell", 0.5), a.get("theta_deg", 0.0)
                    )
                elif c.name == "plane_map":
                    r = t_plane_map(h, a["planes"], a["x0"], a["y0"], a["x1"], a["y1"], a.get("cell", 0.33))
                elif c.name == "roof_edge":
                    r = t_roof_edge(h, a["rays"])
                elif c.name == "submit_label":
                    missing = [v for f in a["facets"] for v in f["ring"] if v not in a["vertices"]]
                    if missing:
                        raise ValueError(f"ring uses undefined vertices: {sorted(set(missing))}")
                    submits += 1
                    label = a
                    (out / f"label_submit{submits}.json").write_text(json.dumps(a, indent=1))
                    truth, facets, edges, polys = lt.build(h, a, "llm_vision", "")
                    truth["_vertices"] = a["vertices"]
                    paths, stats = lt.overlay(
                        h,
                        truth,
                        facets,
                        edges,
                        polys,
                        out / f"overlay_submit{submits}.png",
                        title=f"submission {submits}:",
                    )
                    summ = {
                        "facets": [
                            {
                                k: f[k]
                                for k in (
                                    "id",
                                    "roof_type",
                                    "pitch_rise",
                                    "aspect_deg",
                                    "rms_m",
                                    "inlier_fraction",
                                    "above_plane_fraction",
                                    "below_plane_fraction",
                                    "points",
                                    "area_sqft",
                                    "valid",
                                )
                            }
                            for f in facets
                        ],
                        "edges": [[e["type"], "-".join(e["v"]), e["length_ft"]] for e in edges],
                        "totals": {
                            k: truth[k]
                            for k in (
                                "squares",
                                "area_sqft",
                                "flat_area_sqft",
                                "pitched_area_sqft",
                                "facet_count",
                                "lengths_ft",
                                "lengths_ft_extra",
                            )
                        },
                        "check": stats,
                    }
                    if submits == 1:
                        r = [
                            {
                                "type": "text",
                                "text": "FIRST submission drawn and checked. Look at both pictures. Fix: yellow returns that are roof (edge too tight), facets with low inlier_fraction (mixed surfaces), wrong edge types (override with edge_types), invalid polygons, facets that do not share vertices. Then call submit_label again with the complete corrected label (final).\n"
                                + json.dumps(summ),
                            }
                        ] + [img_block(p) for p in paths]
                    else:
                        r = "Final label recorded. " + json.dumps(summ["totals"])
                        final = True
                else:
                    r = f"unknown tool {c.name}"
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": r})
            except Exception as e:  # noqa: BLE001 - a failing tool is reported back to the model as an error result
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": c.id,
                        "content": f"error: {type(e).__name__}: {e}",
                        "is_error": True,
                    }
                )
        if (
            resp.stop_reason == "max_tokens"
        ):  # cut off AFTER tool calls: every tool_use still needs its tool_result (a plain text reply is a 400)
            results.append(
                {
                    "type": "text",
                    "text": "Your reply was cut off after these tool calls. Continue with smaller steps.",
                }
            )
        left = max_turns - turns
        if left in (5, 2) and not final:
            results.append({"type": "text", "text": f"{left} turns left. Submit now if you have not."})
        spent = cost_of(usage)
        if not final and spent > max_cost:
            stop = "cost_cap"
            break
        if not final and spent > 0.7 * max_cost and not warned:
            warned = True
            results.append(
                {
                    "type": "text",
                    "text": "The budget for this house is nearly used. Submit now: one more submission is all that is left.",
                }
            )
        try:
            audit(results, toks, f"tool results turn {turns}")
        except SystemExit as e:
            print(e, flush=True)
            stop = "privacy_abort"
            break
        transcript[-1]["results"] = [
            (r.get("content") if isinstance(r.get("content"), str) else "[pictures + check]")[:6000]
            if r["type"] == "tool_result"
            else r.get("text")
            for r in results
        ]
        messages.append({"role": "user", "content": results})
        if final:
            stop = "submitted_final"
            break
    runinfo = {
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "effort": effort,
        "turns": turns,
        "submissions": submits,
        "stop": stop,
        "seconds": round(time.time() - t0),
        "usage": usage,
        "cost_usd": round(cost_of(usage), 2),
        "price_per_mtok": PRICE,
        "log": log,
        "models_seen": sorted(models),
        "tag": tag,
    }
    (out / "run.json").write_text(json.dumps(runinfo, indent=1))
    (out / "transcript.json").write_text(json.dumps(transcript, indent=1, default=str))
    log_spend(spend, h.house_id, tag, usage, cost_of(usage), stop)
    if label is None:
        print("NO LABEL", stop)
        return runinfo
    prov = f"{MODEL} via Messages API (served by {sorted(models)}), {PROMPT_VERSION}, effort {effort}, {turns} turns, {submits} submission(s), stop={stop}, run {tag}; inputs: LiDAR renders"
    truth, facets, edges, polys = lt.build(h, label, "llm_vision", prov)
    truth["_vertices"] = label["vertices"]
    paths, stats = lt.overlay(h, truth, facets, edges, polys, out / "overlay_final.png", title="final:")
    del truth["_vertices"]
    truth["vertices"] = label["vertices"]
    truth["label_check"] = stats
    truth["api_run"] = {k: runinfo[k] for k in ("turns", "submissions", "stop", "cost_usd", "usage")}
    if submits < 2:
        truth["confidence"] = "low"
        truth["notes"] = "(not self-corrected: only one submission) " + truth.get("notes", "")
    finalize(truth, h.z0, tag)
    dest = (
        (Path(truth_root) / h.house_id / f"truth.llm_vision.{tag}.json")
        if truth_root
        else (out / "truth.llm_vision.api.json")
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(truth, indent=1))
    print(
        "wrote",
        dest.name,
        {k: truth[k] for k in ("squares", "facet_count", "lengths_ft", "confidence")},
        f"cost ${runinfo['cost_usd']}",
    )
    return runinfo
