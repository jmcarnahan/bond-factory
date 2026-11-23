"""The private data root and what is read from it.

Layout under ``$ROOF_EVAL_DATA`` (nothing of it lives in this repo)::

    manifest.json                       list of rows: id "h-xxxxxxxx", split tuning|heldout|negative|excluded, strata, tiers, flags
    houses/<id>/points.npy              (N,3) library roof points, local metres, absolute z
    houses/<id>/points_wide.npy         (M,4) x, y, z, class (2 = ground)
    houses/<id>/footprint.json          wall outline polygon, local metres
    houses/<id>/meta.json               frame, density, parcel_match, outline_source
    houses/<id>/reference_points.npy    frozen reference roof points (derived once by ``reference_points`` if absent)
    houses/<id>/envelope.json           stored library result (library adapter)
    houses/<id>/orthophoto.png          optional, drawn in blind sheets
    truth/<id>/truth.<source>.json      schema v2 (plan 3.5)
    baselines/<name>/{metrics.json, results/<id>.json}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from .geom import mk_poly

REF_RULE = "ref-v1"
REF_MIN_HEIGHT_M = 1.5
REF_FOOTPRINT_BUFFER_M = 1.2
NON_ROOF_CLASSES = (2, 3, 4, 5, 7, 9)  # ground, vegetation, noise, water
REF_PARAMS = {"min_height_m": REF_MIN_HEIGHT_M, "footprint_buffer_m": REF_FOOTPRINT_BUFFER_M,
              "excluded_classes": list(NON_ROOF_CLASSES), "ground": "median of the 6 nearest class-2 returns (5th percentile of z when < 6)",
              "dedupe_mm": 1, "sort": "x,y,z"}
REF_HASH = hashlib.sha256(json.dumps(REF_PARAMS, sort_keys=True).encode()).hexdigest()[:12]
REBUILD_CMD = "python -m tools.roof_eval reference --rebuild   (make roof-reference REBUILD=1)"
SPLITS = ("tuning", "heldout", "negative", "excluded")
TIER_PREFIX = (("vendor", "T1"), ("synthetic", "T6"), ("llm", "T2"), ("contractor", "T3"), ("manual", "T4"), ("field", "T7"), ("site_check", "T7"))
POOLED = ("pitched", "flat+mixed", "complex")


class DataError(RuntimeError):
    """The data root is missing or malformed."""


def data_root(arg: str | os.PathLike | None = None) -> Path:
    """The data root: ``arg`` or ``$ROOF_EVAL_DATA``; a clear error when neither is set or it does not exist."""
    v = str(arg) if arg else os.environ.get("ROOF_EVAL_DATA", "")
    if not v:
        raise DataError("no data root: set ROOF_EVAL_DATA (or pass --data) to the unpacked regression set")
    p = Path(v).expanduser()
    if not p.is_dir():
        raise DataError(f"data root {p} is not a directory")
    return p


def load_manifest(root: Path) -> list[dict[str, Any]]:
    f = root / "manifest.json"
    if not f.is_file():
        raise DataError(f"{f} is missing")
    m = json.loads(f.read_text())
    rows = m.get("rows", m.get("houses")) if isinstance(m, dict) else m
    if not isinstance(rows, list):
        raise DataError("manifest.json must be a list of rows (or {rows: [...]})")
    return rows


def row_values(row: dict[str, Any], key: str) -> list[str]:
    """A row field as a list of strings (list fields as their members; a missing field as an empty list)."""
    v = row.get(key)
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]


WHERE_RE = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(>=|<=|!=|=|>|<)\s*(.*?)\s*$")


def parse_where(exprs: list[str] | None) -> list[tuple[str, str, set[str]]]:
    """``key=a,b``, ``key!=a`` or a numeric ``key>=6`` (also <=, >, <) into (key, op, values); list fields match when any
    member matches; a numeric comparison on a missing or non-numeric field is false."""
    out = []
    for e in exprs or []:
        m = WHERE_RE.match(e)
        if not m:
            raise DataError(f"bad --where expression {e!r}")
        out.append((m.group(1), m.group(2), {x.strip() for x in m.group(3).split(",")}))
    return out


NUM_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b}


def matches(row: dict[str, Any], where: list[tuple[str, str, set[str]]]) -> bool:
    for k, op, vals in where:
        if op in NUM_OPS:
            try:
                ok = NUM_OPS[op](float(row.get(k)), float(next(iter(vals))))
            except (TypeError, ValueError):
                ok = False
            if not ok:
                return False
            continue
        hit = bool(set(row_values(row, k)) & vals)
        if hit == (op == "!="):
            return False
    return True


def select_rows(rows: list[dict[str, Any]], split: str, where: list[str] | None = None) -> list[dict[str, Any]]:
    """Rows of a split: tuning|heldout|negative, demo (flags include demo or canary), all (everything not excluded)."""
    w = parse_where(where)
    out = []
    for r in rows:
        s = r.get("split")
        if split == "all":
            ok = s != "excluded"
        elif split == "demo":
            ok = bool({"demo", "canary"} & set(row_values(r, "flags"))) or bool(r.get("demo") or r.get("canary"))
        else:
            ok = s == split
        if ok and matches(r, w):
            out.append(r)
    return sorted(out, key=lambda r: r["id"])


def tier_of(source: str) -> str:
    """Truth tier of a source name by prefix (vendor_report -> T1, llm_vision -> T2, contractor_squares -> T3, ...)."""
    return next((t for p, t in TIER_PREFIX if source.startswith(p)), source)


def is_canary(row: dict[str, Any]) -> bool:
    """A demo canary (``canary`` true or flag canary/demo): never evidence, reported in its own section."""
    return bool(row.get("canary")) or bool({"canary", "demo"} & set(row_values(row, "flags")))


def pooled_stratum(row: dict[str, Any]) -> str:
    """Gate pooling (plan 3.7a): complex = manifest complexity >= 10 (``complex(...)`` or ``cut_up``); flat+mixed = flat,
    mixed or commercial and not complex; pitched = the rest (shingle, tile)."""
    rc = str(row.get("roof_class", ""))
    if str(row.get("complexity", "")).startswith(("complex", "cut_up")):
        return "complex"
    return "flat+mixed" if rc in ("flat", "mixed", "commercial") else "pitched"


def house_dir(root: Path, hid: str) -> Path:
    return root / "houses" / hid


def load_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def parse_polygon(obj) -> Polygon:
    """A wall outline from a ring, {polygon|ring|exterior|coordinates|wkt: ...} or a GeoJSON-like dict."""
    if obj is None:
        return Polygon()
    if isinstance(obj, dict):
        if obj.get("wkt"):
            from shapely import wkt

            g = wkt.loads(obj["wkt"])
            return g if isinstance(g, Polygon) else max(getattr(g, "geoms", [Polygon()]), key=lambda q: q.area)
        for k in ("polygon", "ring", "exterior", "coordinates", "outline", "footprint", "geometry"):
            if k in obj:
                return parse_polygon(obj[k])
        return Polygon()
    if obj and isinstance(obj[0], (list, tuple)) and obj[0] and isinstance(obj[0][0], (list, tuple)):
        return parse_polygon(obj[0]) if len(obj) == 1 else mk_poly(obj)
    return mk_poly(obj)


@dataclass
class House:
    id: str
    dir: Path
    row: dict[str, Any]

    def meta(self) -> dict[str, Any]:
        return load_json(self.dir / "meta.json", {}) or {}

    def footprint(self) -> Polygon:
        return parse_polygon(load_json(self.dir / "footprint.json"))

    def wide(self) -> np.ndarray:
        return np.load(self.dir / "points_wide.npy").astype(np.float64)

    def reference(self) -> np.ndarray:
        return reference_points(self.dir)


def ground_function(w: np.ndarray):
    """Local ground height: median of the 6 nearest class-2 returns; a low percentile when ground is scarce."""
    g = w[w[:, 3] == 2]
    if len(g) >= 6:
        tree = cKDTree(g[:, :2])

        def at(xy):
            _, i = tree.query(xy, k=6)
            return np.median(g[i, 2], axis=1)

        return at
    z0 = float(np.percentile(w[:, 2], 5)) if len(w) else 0.0
    return lambda xy: np.full(len(xy), z0)


def derive_reference(w: np.ndarray, footprint: Polygon) -> np.ndarray:
    """Rule ref-v1, independent of any engine output: returns of ``points_wide`` that are not ground, vegetation,
    noise or water, lie more than 1.5 m above the local ground and fall inside the wall outline buffered by 1.2 m.
    Duplicates at 1 mm are dropped; rows are sorted by (x, y, z) so the file is deterministic."""
    if len(w) == 0 or footprint.is_empty:
        return np.zeros((0, 3))
    keep = ~np.isin(w[:, 3], NON_ROOF_CLASSES)
    c = w[keep][:, :3]
    c = c[c[:, 2] - ground_function(w)(c[:, :2]) > REF_MIN_HEIGHT_M]
    inside = shapely.intersects_xy(footprint.buffer(REF_FOOTPRINT_BUFFER_M), c[:, 0], c[:, 1])
    c = c[inside]
    c = c[np.unique(np.round(c * 1000).astype(np.int64), axis=0, return_index=True)[1]]
    return c[np.lexsort((c[:, 2], c[:, 1], c[:, 0]))]


class StaleReference(DataError):
    """A stored reference_points.npy was not made by the current rule (version or parameter hash differs)."""


def reference_status(hdir: Path) -> str:
    """``missing`` (no file: derived on first use), ``ok`` (sidecar rule and parameter hash match) or ``stale``."""
    if not (hdir / "reference_points.npy").is_file():
        return "missing"
    side = load_json(hdir / "reference_points.json", {}) or {}
    return "ok" if side.get("rule") == REF_RULE and side.get("params_hash") == REF_HASH else "stale"


def write_reference(hdir: Path, ref: np.ndarray, **extra: Any) -> None:
    np.save(hdir / "reference_points.npy", ref.astype(np.float32))
    (hdir / "reference_points.json").write_text(json.dumps(
        {"rule": REF_RULE, "params_hash": REF_HASH, "params": REF_PARAMS, "n": len(ref), **extra}, sort_keys=True))


def reference_points(hdir: Path, write: bool = True) -> np.ndarray:
    """The frozen reference points of a house dir. A stored file is read only when its sidecar carries the current rule
    version and parameter hash; otherwise StaleReference (never a silent stale read; rebuild with ``REBUILD_CMD``). Absent:
    derived and written once (``write=False``: derived in memory only, for houses outside the regression set)."""
    f = hdir / "reference_points.npy"
    if reference_status(hdir) == "stale":
        raise StaleReference(f"{hdir.name}: reference_points.npy was not made by rule {REF_RULE}/{REF_HASH}; rebuild with {REBUILD_CMD}")
    if f.is_file():
        return np.load(f).astype(np.float64)[:, :3]
    ref = derive_reference(np.load(hdir / "points_wide.npy").astype(np.float64),
                           parse_polygon(load_json(hdir / "footprint.json")))
    if not write:
        return ref
    write_reference(hdir, ref)
    return np.load(f).astype(np.float64)


def check_references(root: Path, ids: list[str]) -> list[str]:
    """Ids of the houses whose stored reference is stale."""
    return [i for i in ids if reference_status(house_dir(root, i)) == "stale"]


def rebuild_references(root: Path) -> dict[str, int]:
    """Re-derive every house's reference with the current rule. A derived house (meta ``derived_from``: thinned or shifted
    copy) gets its parent's reference, frozen at full density; a derived house whose parent is not here is reported."""
    hs = sorted(p for p in (root / "houses").iterdir() if p.is_dir())
    out = {"derived": 0, "copied": 0, "orphans": 0}
    kids = []
    for h in hs:
        parent = (load_json(h / "meta.json", {}) or {}).get("derived_from")
        if parent:
            kids.append((h, parent))
            continue
        write_reference(h, derive_reference(np.load(h / "points_wide.npy").astype(np.float64),
                                            parse_polygon(load_json(h / "footprint.json"))))
        out["derived"] += 1
    for h, parent in kids:
        src = root / "houses" / parent
        if not (src / "reference_points.npy").is_file():
            out["orphans"] += 1
            continue
        write_reference(h, np.load(src / "reference_points.npy"), derived_from=parent)
        out["copied"] += 1
    return out


def load_truths(root: Path, hid: str) -> list[dict[str, Any]]:
    """truth/<id>/truth.<source>.json files, each with ``tier`` and ``file`` added; sorted by file name."""
    out = []
    for p in sorted((root / "truth" / hid).glob("truth.*.json")):
        t = load_json(p)
        if isinstance(t, dict):
            src = str(t.get("source") or p.name.split(".")[1])
            t = {**t, "file": p.name, "tier": tier_of(src)}
            out.append(t)
    return out
