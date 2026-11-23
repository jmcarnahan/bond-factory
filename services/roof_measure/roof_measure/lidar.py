"""USGS 3DEP LiDAR over HTTPS (Entwine Point Tile), keyless.

WHY EPT: the 3DEP archive is huge, but EPT lets us read only the octree nodes that touch a
~100 m box (a few MB) instead of whole tiles. Project selection uses the hobu `resources.geojson`
boundaries, ranked newest first, so the caller can fall through to an older survey when the
newest has no data at the address.
"""

from __future__ import annotations

import io
import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import laspy
import lazrs
import numpy as np
import requests
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import Point, Polygon, shape

from . import cache
from .frame import project_geometry

log = logging.getLogger(__name__)

RESOURCES_URL = "https://raw.githubusercontent.com/hobuinc/usgs-lidar/master/boundaries/resources.geojson"
EPT_BASE = "https://usgs-lidar-public.s3.amazonaws.com/"
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=UTC)
ADJUSTED_GPS_OFFSET_S = 1e9  # LAS "adjusted standard GPS time" = GPS seconds - 1e9


class LidarError(RuntimeError):
    """No LiDAR covers the address."""


def is_outage(exc: BaseException) -> bool:
    """A request failure that may pass: connection trouble and HTTP 5xx/429. An HTTP 4xx (a missing tile) is permanent."""
    if not isinstance(exc, requests.RequestException):
        return False
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return not (status is not None and 400 <= status < 500 and status != 429)


class LidarUnavailable(LidarError):
    """The LiDAR source could not be reached (outage, rate limit): retryable, not 'no coverage here'."""


class LidarTooSparse(LidarError):
    """LiDAR exists but is too thin on the roof to segment (message names project, year, density)."""

    def __init__(self, project: str | None, year: int | None, density: float, needed: float):
        self.project, self.year, self.density = project, year, density
        super().__init__(f"LiDAR is too sparse on this roof: {project or 'unknown project'} "
                         f"({year or 'year unknown'}) gives {density:.1f} points/m2 inside the footprint; "
                         f"at least {needed:.0f} are needed.")


DENSE_ENOUGH = 8.0  # expected points/m2 from which a survey is good enough to prefer the newest of them
MAX_CANDIDATES = 3  # projects tried for one building (each costs LiDAR tile downloads), best expected density first
MIN_ROOF_DENSITY = 4.0  # points per m2 inside the footprint below which the job fails (plan D17); below 8 warns


@dataclass
class LidarProject:
    name: str
    ept_url: str
    year: int | None
    density: float  # project-wide points per m2 (count / boundary area); a ranking proxy
    span_m: float  # longest side of the project's bounding box in metres
    count: int = 0
    srs_epsg: int = 3857
    ept: dict = field(default_factory=dict, repr=False)


def rank_projects(projects: list[LidarProject]) -> list[LidarProject]:
    """Dense-enough surveys (``DENSE_ENOUGH``) newest first; then surveys of unknown density, newest first; then the
    known-thin ones, densest first (newest the tie-break).

    WHY: a thin new survey (5 points/m2) cannot draw a roof that an older 13 points/m2 survey can, but among surveys
    that are dense enough the newest wins: roofs change (re-roofs, additions), so a 2016 survey at 20 points/m2 must not
    beat a 2023 one at 15. A listing without a point count (density 0) is unknown, not thin: it is tried before the
    known-thin ones. Density is the project-wide average (a proxy, compared to 0.1 points/m2);
    ``fetch_best_points`` checks the density on the roof itself.
    """
    def key(lp: LidarProject) -> tuple[int, float, float]:
        d, y = round(lp.density, 1), float(lp.year or 0)
        if d >= DENSE_ENOUGH:
            return (0, -y, -d)
        return (1, -y, 0.0) if d <= 0 else (2, -d, -y)

    return sorted(projects, key=key)


@dataclass
class PointCloud:
    """Points in a metric CRS (`meta['epsg']`); z in metres."""

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    classification: np.ndarray
    gps_time: np.ndarray
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.x)

    def save_npz(self, path: str | Path) -> None:
        """Write a compressed `.npz`; meta rides along as a JSON string. Never commit these."""
        np.savez_compressed(path, x=self.x, y=self.y, z=self.z, classification=self.classification,
                            gps_time=self.gps_time, meta=np.array(json.dumps(self.meta)))

    @classmethod
    def from_npz(cls, path: str | Path | io.IOBase) -> PointCloud:
        """Load our own files and the research ones (keys `cls`/`gps` are accepted)."""
        d = np.load(path, allow_pickle=False)
        keys = set(d.files)
        cl = d["classification"] if "classification" in keys else d["cls"]
        if "gps_time" in keys:
            gps = d["gps_time"]
        elif "gps" in keys:
            gps = d["gps"]
        else:
            gps = np.zeros(len(d["x"]))
        meta = json.loads(str(d["meta"])) if "meta" in keys else {}
        return cls(d["x"], d["y"], d["z"], cl, gps, meta)

    def subset(self, mask: np.ndarray) -> PointCloud:
        return PointCloud(self.x[mask], self.y[mask], self.z[mask], self.classification[mask],
                          self.gps_time[mask], dict(self.meta))


save_npz = PointCloud.save_npz


def load_npz(path: str | Path) -> PointCloud:
    return PointCloud.from_npz(path)


def gps_to_date(gps_adjusted: float) -> str:
    """Adjusted GPS time (seconds) -> ISO date. Leap seconds ignored: day precision is enough."""
    return (GPS_EPOCH + timedelta(seconds=float(gps_adjusted) + ADJUSTED_GPS_OFFSET_S)).date().isoformat()


def acquired_range(gps: np.ndarray) -> str | None:
    """'YYYY-MM-DD/YYYY-MM-DD' from a GPS-time array, or None when times are absent."""
    g = gps[np.isfinite(gps) & (gps != 0)]
    if g.size == 0:
        return None
    return f"{gps_to_date(g.min())}/{gps_to_date(g.max())}"


# ------------------------------------------------------------------ project selection
def project_year(name: str) -> int | None:
    """Acquisition year from a project name, or None when the name does not say.

    Order: an explicit 4-digit year token anywhere (first one wins), else a TRAILING `_B23`/`_D23`/`_A23`
    style token (20xx). A block number in the middle (`AK_NorthSlope_B10_2018`) is never a year.
    """
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", name)
    if m:
        return int(m.group(1))
    m = re.search(r"_[A-Za-z](\d{2})$", name)
    return 2000 + int(m.group(1)) if m else None


def sample_year(ept_url: str, ept: dict) -> int | None:
    """Year of a project whose name has none, from the GPS time of the root octree node (one small fetch)."""
    try:
        base = ept_url.rsplit("/", 1)[0] + "/"
        las = laspy.read(io.BytesIO(cache.fetch_bytes(f"{base}ept-data/0-0-0-0.laz", max_age_s=365 * cache.DAY)))
        t = np.asarray(las.gps_time)
        t = t[t != 0]
        if t.size == 0:
            return None
        year = int(gps_to_date(float(np.median(t)))[:4])
        return year if 1995 <= year <= 2040 else None
    except (*cache.NET_ERRORS, laspy.errors.LaspyException):
        return None


def _load_resources() -> list[dict]:
    def check(obj: object) -> None:
        if not isinstance(obj, dict) or not isinstance(obj.get("features"), list) or not obj["features"]:
            raise cache.BadResponse("resources.geojson is not a GeoJSON FeatureCollection")

    body = cache.fetch_bytes(RESOURCES_URL, max_age_s=30 * cache.DAY, timeout=120,
                             validate=cache.json_validator(check))
    return json.loads(body)["features"]


def _quick_bbox_contains(geom: dict, lng: float, lat: float) -> bool:
    """Cheap reject before building a shapely geometry for 2,000+ boundaries."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        ring = poly[0]
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        if min(xs) <= lng <= max(xs) and min(ys) <= lat <= max(ys):
            return True
    return False


def select_project(lat: float, lng: float) -> list[LidarProject]:
    """All 3DEP projects covering the point, dense-enough surveys newest first, then the rest densest first (``rank_projects``)."""
    out: list[LidarProject] = []
    pt = Point(lng, lat)
    for f in _load_resources():
        if not f.get("geometry") or not _quick_bbox_contains(f["geometry"], lng, lat):
            continue
        g = shape(f["geometry"])
        if not g.contains(pt):
            continue
        p = f["properties"]
        name = p["name"]
        url = p.get("url") or f"{EPT_BASE}{name}/ept.json"
        # 3857 areas are inflated by 1/cos^2(lat); correct with the point's latitude.
        g_m = project_geometry(g, 4326, 3857)
        area_m2 = g_m.area * math.cos(math.radians(lat)) ** 2
        minx, miny, maxx, maxy = g_m.bounds
        span = max(maxx - minx, maxy - miny) * math.cos(math.radians(lat))
        count = int(p.get("count") or 0)
        out.append(LidarProject(name=name, ept_url=url, year=project_year(name),
                                density=count / area_m2 if area_m2 else 0.0, span_m=float(span), count=count))
    out = rank_projects(out)
    for lp in out:
        try:
            lp.ept = cache.fetch_json(lp.ept_url, max_age_s=30 * cache.DAY, check=_ept_check)
            srs = lp.ept.get("srs", {})
            lp.srs_epsg = int(srs.get("horizontal") or 3857)
            if lp.year is None:
                lp.year = sample_year(lp.ept_url, lp.ept)
        except (*cache.NET_ERRORS, LidarError) as e:  # keep the project listed; fetch_points will fail loudly
            log.warning("could not read an EPT project: %s", cache.describe_error(e))
    return rank_projects(out)  # again: sampled years may have changed the tie-breaks


def _ept_check(obj: object) -> None:
    if not isinstance(obj, dict) or "bounds" not in obj or "schema" not in obj:
        raise cache.BadResponse("ept.json is missing bounds/schema")


# ------------------------------------------------------------------ point fetch
_VERTICAL_FEET = {6360: 0.3048006096012192, 8228: 0.3048, 6359: 0.3048}  # NAVD88 height in US survey / intl feet
CORRUPT_LAZ = (laspy.errors.LaspyException, ValueError, EOFError, RuntimeError, lazrs.LazrsError)


def vertical_scale(ept: dict) -> tuple[float, str | None]:
    """(metres per z unit, warning). Reads the EPT `srs`: a VERT_CS unit in the WKT, else the vertical EPSG code.

    WHY: 3DEP projects are mostly metres, but a feet project would silently read every height 3.28x too
    large. When the unit cannot be determined we assume metres and say so (the model layer surfaces it).
    """
    srs = ept.get("srs", {}) or {}
    wkt = str(srs.get("wkt") or "")
    m = re.search(r'VERT_CS\[.*?UNIT\["([^"]+)",\s*([\d.]+)', wkt, re.DOTALL)
    if m:
        return float(m.group(2)), None
    vert = str(srs.get("vertical") or "").strip()
    if vert.isdigit():
        code = int(vert)
        if code in _VERTICAL_FEET:
            return _VERTICAL_FEET[code], None
        return 1.0, None
    return 1.0, "LiDAR vertical unit is not declared in the EPT metadata; assumed metres."

def fetch_points(project: LidarProject, center_lat: float, center_lng: float, half_size_m: float,
                 epsg_out: int) -> PointCloud:
    """Read the EPT nodes under a square box of half-side `half_size_m` centred on the point.

    WHY clip twice: nodes are cube-shaped and much bigger than the box, so each node is
    clipped in the EPT CRS first (cheap) and the final box again in the output CRS.
    """
    base = project.ept_url.rsplit("/", 1)[0] + "/"
    ept = project.ept or json.loads(cache.fetch_bytes(project.ept_url, max_age_s=30 * cache.DAY))
    cube = ept["bounds"]
    ept_epsg = int(ept.get("srs", {}).get("horizontal") or 3857)
    to_out = Transformer.from_crs(4326, epsg_out, always_xy=True)
    out_to_ept = Transformer.from_crs(epsg_out, ept_epsg, always_xy=True)
    ept_to_out = Transformer.from_crs(ept_epsg, epsg_out, always_xy=True)
    cx, cy = to_out.transform(center_lng, center_lat)
    x0, y0, x1, y1 = cx - half_size_m, cy - half_size_m, cx + half_size_m, cy + half_size_m
    cs = [out_to_ept.transform(x, y) for x, y in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]]
    mx0, mx1 = min(c[0] for c in cs), max(c[0] for c in cs)
    my0, my1 = min(c[1] for c in cs), max(c[1] for c in cs)

    z_scale, z_warning = vertical_scale(ept)

    def get(u: str, validate: cache.Validator | None = None) -> bytes:
        return cache.fetch_bytes(u, max_age_s=365 * cache.DAY, timeout=60, validate=validate)

    def _hier_check(o: object) -> None:
        if not isinstance(o, dict) or not o:
            raise cache.BadResponse("ept-hierarchy page is not a non-empty JSON object")

    def touches(d: int, x: int, y: int) -> bool:
        sx = (cube[3] - cube[0]) / 2**d
        sy = (cube[4] - cube[1]) / 2**d
        a, b = cube[0] + x * sx, cube[1] + y * sy
        return a <= mx1 and a + sx >= mx0 and b <= my1 and b + sy >= my0

    hier: dict[str, int] = {}

    def load_h(k: str) -> None:
        hier.update(json.loads(get(f"{base}ept-hierarchy/{k}.json", cache.json_validator(_hier_check))))

    load_h("0-0-0-0")
    want: list[str] = []
    stack, seen = ["0-0-0-0"], set()
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        d, x, y, z = (int(v) for v in k.split("-"))
        if not touches(d, x, y) or k not in hier:
            continue
        n = hier[k]
        if n == -1:
            load_h(k)  # subtree page
            n = hier.get(k, 0)
        if n > 0:
            want.append(k)
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    c = f"{d + 1}-{2 * x + dx}-{2 * y + dy}-{2 * z + dz}"
                    if c in hier:
                        stack.append(c)
    cols: dict[str, list[np.ndarray]] = {"x": [], "y": [], "z": [], "c": [], "t": []}
    for k in want:
        url = f"{base}ept-data/{k}.laz"
        try:
            las = laspy.read(io.BytesIO(get(url)))
        except CORRUPT_LAZ as e:
            cache.evict(url)  # a truncated or garbled download must not be served again
            raise LidarError(f"{project.name}: corrupt LiDAR node {k} ({e}); removed from the cache, retry.") from e
        X, Y = np.asarray(las.x), np.asarray(las.y)
        m = (X >= mx0) & (X <= mx1) & (Y >= my0) & (Y <= my1)
        if not m.any():
            continue
        ux, uy = ept_to_out.transform(X[m], Y[m])
        cols["x"].append(ux)
        cols["y"].append(uy)
        cols["z"].append(np.asarray(las.z)[m] * z_scale)
        cols["c"].append(np.asarray(las.classification)[m])
        cols["t"].append(np.asarray(las.gps_time)[m])
    if not cols["x"]:
        raise LidarError(f"{project.name} has no points within {half_size_m:.0f} m of the address.")
    A = {k: np.concatenate(v) for k, v in cols.items()}
    m = (A["x"] >= x0) & (A["x"] <= x1) & (A["y"] >= y0) & (A["y"] <= y1)
    meta = {"project": project.name, "year": project.year, "epsg": epsg_out, "center": [cx, cy],
            "half_size_m": half_size_m, "box_m": 2 * half_size_m, "acquired": acquired_range(A["t"][m]), "nodes": len(want),
            "z_scale": z_scale, "warnings": [z_warning] if z_warning else []}
    return PointCloud(A["x"][m], A["y"][m], A["z"][m], A["c"][m].astype(np.uint8), A["t"][m], meta)


def footprint_density(pc: PointCloud, footprint_m: Polygon) -> float:
    """Non-ground returns per m2 strictly inside the footprint (a cheap stand-in for roof density)."""
    inside = contains_xy(footprint_m, pc.x, pc.y) & (pc.classification != 2)
    return float(inside.sum() / footprint_m.area) if footprint_m.area else 0.0


def fetch_best_points(lat: float, lng: float, half_size_m: float, epsg_out: int, min_points: int = 2000,
                      footprint_m: Polygon | None = None) -> PointCloud:
    """Try ranked projects (``rank_projects``; at most ``MAX_CANDIDATES``) until one has enough points on the roof.

    With `footprint_m` (metres in `epsg_out`) the test is roof density inside the footprint, so ground and
    trees in the box cannot make a thin survey pass; otherwise `min_points` counts the whole box. A survey that passes
    but gives under ``DENSE_ENOUGH`` points/m2 ON THE ROOF does not end the search while candidates remain: the next is
    fetched and the cloud with the higher roof density wins (a project average of 9 can mean 5 on one roof).
    `meta['fallback_used']` is True when the winner was not the first-ranked project; `meta['roof_density']` and
    `meta['choice']` say what it gave and why it won.
    """
    try:
        projects = select_project(lat, lng)
    except cache.NET_ERRORS as e:
        # only request/HTTP failures are outages; a body that does not parse is bad data (permanent)
        kind = LidarUnavailable if is_outage(e) else LidarError
        raise kind(f"Could not list USGS 3DEP projects ({cache.describe_error(e)}).") from e
    if not projects:
        raise LidarError("No USGS 3DEP LiDAR project covers this address.")
    projects = rank_projects(projects)[:MAX_CANDIDATES]  # whoever listed them, the order and the bound are ours
    reasons: list[str] = []
    net_failures = 0
    thin: tuple[LidarProject, float] | None = None
    best: tuple[PointCloud, float, int, LidarProject] | None = None  # (cloud, roof density, rank, project)
    for i, p in enumerate(projects):
        if best is not None and best[1] >= DENSE_ENOUGH:
            break
        try:
            pc = fetch_points(p, lat, lng, half_size_m, epsg_out)
        except (*cache.NET_ERRORS, LidarError) as e:
            net_failures += is_outage(e)
            reasons.append(f"{p.name}: {cache.describe_error(e) if isinstance(e, cache.NET_ERRORS) else e}")
            log.warning("project %s failed: %s", p.name, cache.describe_error(e))
            continue
        if footprint_m is not None:
            dens = footprint_density(pc, footprint_m)
            if dens < MIN_ROOF_DENSITY:
                reasons.append(f"{p.name}: {dens:.1f} points/m2 inside the footprint")
                if thin is None or dens > thin[1]:
                    thin = (p, dens)
                continue
        elif len(pc) < min_points:
            reasons.append(f"{p.name}: only {len(pc)} points")
            continue
        else:
            dens = float("inf")  # no footprint, no roof density: the first survey with enough points is the answer
        if best is None or dens > best[1]:
            if best is not None:
                reasons.append(f"{best[3].name}: {best[1]:.1f} points/m2 on the roof, beaten by {p.name}")
            best = (pc, dens, i, p)
        else:
            reasons.append(f"{p.name}: {dens:.1f} points/m2 on the roof, below {best[3].name}")
    if best is not None:
        pc, dens, i, p = best
        pc.meta["fallback_used"] = i > 0
        pc.meta["skipped"] = reasons
        if dens != float("inf"):
            pc.meta["roof_density"] = round(dens, 1)
            pc.meta["choice"] = (f"{p.name} gives {dens:.1f} points/m2 on the roof"
                                 + ("" if dens >= DENSE_ENOUGH else f" (the best of the surveys tried; under {DENSE_ENOUGH:g})"))
        return pc
    if thin is not None:
        raise LidarTooSparse(thin[0].name, thin[0].year, thin[1], MIN_ROOF_DENSITY)
    detail = "No 3DEP project returned usable points near this address: " + "; ".join(reasons)
    raise (LidarUnavailable if net_failures == len(projects) else LidarError)(detail)


def fetch_for_footprint(footprint_m: Polygon, epsg: int, *, margin_m: float = 15.0) -> PointCloud:
    """Fetch LiDAR sized to the building: a square box of half-side (longest bbox side)/2 + `margin_m`.

    WHY not a fixed box: a 344 ft building does not fit in 60 m. The margin keeps ground returns around
    the walls for the ground estimate. The box is centred on the footprint bbox centre.
    """
    minx, miny, maxx, maxy = footprint_m.bounds
    half = max(maxx - minx, maxy - miny) / 2 + margin_m
    lng, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform((minx + maxx) / 2, (miny + maxy) / 2)
    return fetch_best_points(lat, lng, half, epsg, footprint_m=footprint_m)
