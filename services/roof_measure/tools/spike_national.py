"""Spike: national hit rate of the current roof pipeline (one OSM house per seed region).

Run: PYTHONPATH=services/roof_measure services/roof_measure/.venv/bin/python -m tools.spike_national
Coordinates and addresses live only in local/spike-sites.json (gitignored); stdout never shows them.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

from roof_measure import blocks as blocks_mod
from roof_measure import cache
from roof_measure import footprint as fp_mod
from roof_measure import geocode as geo_mod
from roof_measure import lidar as lidar_mod
from roof_measure.deadline import Deadline
from roof_measure.errors import error_from
from roof_measure.pipeline import run_pipeline
from roof_measure.text import slug

SEEDS = {  # state: (city, lat, lng)
    "TX": ("Austin", 30.37, -97.76), "FL": ("Orlando", 28.47, -81.44),
    "NY": ("Rochester", 43.20, -77.60), "CO": ("Fort Collins", 40.55, -105.07),
    "WA": ("Spokane", 47.67, -117.38), "CA": ("Los Angeles", 33.98, -118.12),
}
REPO = Path(__file__).resolve().parents[3]
SCRATCH = Path("/private/tmp/claude-501/-Users-johncarnahan-projects-bond-factory/"
               "2427435e-5cab-4196-ab9a-c70794376cd2/scratchpad/roof-module-v1/spike-national")
STAGES: dict[str, float] = {}
SEEN: dict[str, Any] = {}
OVERPASS_LOG: list[str] = []


def _dist_m(lat: float, lng: float, la: float, ln: float) -> float:
    return math.hypot((la - lat) * 111_000, (ln - lng) * 111_000 * math.cos(math.radians(lat)))


def _tagged(tags: dict) -> bool:
    return bool(tags.get("addr:housenumber") and tags.get("addr:street"))


PICK_MIRRORS = ("https://lz4.overpass-api.de/api/interpreter", "https://overpass-api.de/api/interpreter",
                "https://z.overpass-api.de/api/interpreter")
BUILDINGS = "house|detached|residential|semidetached_house"


def _overpass(q: str, tag: str) -> list[dict] | None:
    for i, url in enumerate(PICK_MIRRORS, 1):
        t0 = time.time()
        try:
            r = requests.post(url, data={"data": q}, timeout=40, headers={"User-Agent": cache.USER_AGENT})
            r.raise_for_status()
            obj = r.json()
            if obj.get("remark"):
                raise ValueError("remark")
            OVERPASS_LOG.append(f"{tag}: mirror {i} ok in {time.time() - t0:.1f}s, {len(obj['elements'])} ways")
            return obj["elements"]
        except Exception as e:  # noqa: BLE001
            OVERPASS_LOG.append(f"{tag}: mirror {i} failed after {time.time() - t0:.1f}s: {type(e).__name__}")
    return None


def pick_house(lat: float, lng: float, radius_m: int = 3000, skip: int = 0) -> dict:
    """Nearest house-like way (preferring address-tagged); tries `radius_m` then 3000 m; `skip` = next tagged."""
    els: list[dict] = []
    for rad in dict.fromkeys((radius_m, 3000)):
        q = f'[out:json][timeout:35];way["building"~"^({BUILDINGS})$"](around:{rad},{lat},{lng});out center 40;'
        els = [e for e in (_overpass(q, f"pick r{rad}") or []) if e.get("center")]
        if any(_tagged(e.get("tags", {})) for e in els):
            break
    if not els:
        raise RuntimeError("pick_failed")
    els.sort(key=lambda e: _dist_m(lat, lng, e["center"]["lat"], e["center"]["lon"]))
    tagged = [e for e in els if _tagged(e.get("tags", {}))]
    el = tagged[skip] if len(tagged) > skip else els[0]
    t = el.get("tags", {})
    return {"lat": el["center"]["lat"], "lng": el["center"]["lon"], "osm_way_id": el["id"],
            "tagged": _tagged(t), "housenumber": t.get("addr:housenumber"), "street": t.get("addr:street"),
            "postcode": t.get("addr:postcode")}


def build_address(h: dict, city: str, state: str) -> str:
    if not h["tagged"]:
        return f"{city}, {state}"
    return f"{h['housenumber']} {h['street']}, {city}, {state}" + (f" {h['postcode']}" if h["postcode"] else "")


def _timed(mod: Any, name: str, key: str) -> None:
    orig = getattr(mod, name)

    def wrapper(*a: Any, **k: Any) -> Any:
        t0 = time.time()
        try:
            res = orig(*a, **k)
            if key == "footprint":
                SEEN["provider"] = getattr(res, "provider", None)
            return res
        finally:
            STAGES[key] = time.time() - t0
    setattr(mod, name, wrapper)


class _Capture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.endswith("footprint") and "Overpass" in record.getMessage():
            OVERPASS_LOG.append(f"footprint: Overpass mirror {record.args[0] if record.args else '?'} failed")


def _read_model(out_dir: Path, address: str) -> dict:
    p = out_dir / f"{slug(address)}_model.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _redact(msg: str) -> str:
    msg = re.sub(r"(?<![\d.])\d{1,6} [A-Z][\w .'-]*", "<addr>", msg)
    msg = re.sub(r"-?\d{1,3}\.\d{3,}", "<num>", msg)
    return msg[:200]


def run_site(state: str, address: str, timeout: float, latlng: tuple[float, float] | None = None) -> dict:
    out_dir = SCRATCH / "out" / state
    STAGES.clear()
    SEEN.clear()
    row: dict[str, Any] = {"state": state, "footprint_source": "n/a", "3dep_project": "n/a",
                           "density_pts_m2": "n/a", "seconds": 0.0, "outcome": "done", "error_code": ""}
    t0 = time.time()
    ex = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"spike-{state}")
    fut = ex.submit(run_pipeline, address, out_dir, "lidar_skeleton", no_agent=True, verify=False,
                    lat_lng=latlng, deadline=Deadline.after(timeout - 2))
    try:
        res = fut.result(timeout=timeout)
        lid = (res.model.get("source", {}) or {}).get("lidar") or {}
        row["3dep_project"] = lid.get("project") or "n/a"
        row["footprint_source"] = res.footprint_source
        d = res.density_pts_m2
        row["density_pts_m2"] = round(d, 1) if isinstance(d, (int, float)) else "n/a"
    except cf.TimeoutError:
        row.update(outcome="timeout", error_code="timeout")
    except Exception as e:  # noqa: BLE001
        err = error_from(e)
        row.update(outcome="failed", error_code=f"{err['code']} ({type(e).__name__})",
                   error_msg=_redact(err["message"])[:150])
        if isinstance(e, lidar_mod.LidarTooSparse):
            row["3dep_project"], row["density_pts_m2"] = e.project or "n/a", round(e.density, 1)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    if row["footprint_source"] == "n/a":
        row["footprint_source"] = SEEN.get("provider") or "n/a"
    row["seconds"] = round(time.time() - t0, 1)
    row["stages_s"] = {k: round(v, 1) for k, v in STAGES.items()}
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--sites", default=str(REPO / "local" / "spike-sites.json"))
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--next", action="store_true", help="re-pick the next-nearest tagged house for --only")
    a = ap.parse_args(argv)
    only = [s for s in a.only.split(",") if s] or list(SEEDS)
    sites_path = Path(a.sites)
    sites: dict[str, dict] = {}
    if sites_path.exists() and (a.reuse or a.next or a.only):
        sites = {s["state"]: s for s in json.loads(sites_path.read_text())}
    logging.getLogger("roof_measure.footprint").addHandler(_Capture())
    logging.getLogger("roof_measure.footprint").setLevel(logging.INFO)
    _timed(geo_mod, "geocode", "geocode")
    _timed(fp_mod, "fetch_footprint", "footprint")
    _timed(lidar_mod, "fetch_for_footprint", "lidar")
    _timed(blocks_mod, "segment_blocks", "blocks")
    rows = []
    for st in only:
        city, lat, lng = SEEDS[st]
        if a.next or st not in sites:
            try:
                h = pick_house(lat, lng, skip=1 if a.next else 0)
            except RuntimeError:
                rows.append({"state": st, "footprint_source": "n/a", "3dep_project": "n/a",
                             "density_pts_m2": "n/a", "seconds": 0.0, "outcome": "pick_failed",
                             "error_code": "OverpassUnavailable"})
                print(json.dumps(rows[-1]), flush=True)
                continue
            sites[st] = {"state": st, "address": build_address(h, city, st), "lat": h["lat"], "lng": h["lng"],
                         "osm_way_id": h["osm_way_id"], "tagged": h["tagged"]}
            sites_path.parent.mkdir(parents=True, exist_ok=True)
            sites_path.write_text(json.dumps(list(sites.values()), indent=1))
        print(f"{st}: site chosen", file=sys.stderr, flush=True)
        ll = (sites[st]["lat"], sites[st]["lng"]) if not sites[st].get("tagged", True) else None
        rows.append(run_site(st, sites[st]["address"] if not ll else f"{st} spike site", a.timeout, ll))
        print(json.dumps(rows[-1]), flush=True)
    cols = ["state", "footprint_source", "3dep_project", "density_pts_m2", "seconds", "outcome", "error_code"]
    print("\n| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    print("\n".join(OVERPASS_LOG))
    return 0


if __name__ == "__main__":
    sys.exit(main())
