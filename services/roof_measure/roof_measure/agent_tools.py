"""The agent's tool workspace: the polygon registry, the tools behind the tool schema, and finalize validation.

Split from agent.py (line cap); ``roof_measure.agent`` re-exports every name.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .classify import RoofBlock, polygons_of, ridge_azimuth, ring_of
from .skeleton import block_geometry, hip_roof_edges, measure, rect_fit, signed_area, split_footprint

NUMBER_TOL = 0.006


def _r(o: Any, nd: int = 3) -> Any:
    """Round floats in nested results so the model copies short, exact numbers."""
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {k: _r(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_r(v, nd) for v in o]
    return o


def _numbers(o: Any) -> list[float]:
    if isinstance(o, bool):
        return []
    if isinstance(o, (int, float)):
        return [float(o)]
    if isinstance(o, dict):
        return [n for v in o.values() for n in _numbers(v)]
    if isinstance(o, (list, tuple)):
        return [n for v in o for n in _numbers(v)]
    return []


# ----------------------------------------------------------------------------- tool workspace
def require_finite(args: Any) -> None:
    """ValueError when a number anywhere in a tool call is NaN or infinite (``1e999`` parses to infinity)."""
    try:
        finite = all(math.isfinite(n) for n in _numbers(args))
    except OverflowError:  # an integer too large for a float
        finite = False
    if not finite:
        raise ValueError("a number in the call is not finite; copy numbers from the evidence table or a tool result")


class Workspace:
    """Server-side state behind the tools: polygon registry and the set of citable numbers."""

    def __init__(self, footprint_ft: list[tuple[float, float]], rows: list[dict[str, Any]],
                 segment_polys: dict[str, Polygon]) -> None:
        self.footprint = [tuple(p) for p in footprint_ft]
        self.polys: dict[str, list[tuple[float, float]]] = {"footprint": self.footprint}
        self.rows = {r["id"]: r for r in rows}
        self.segment_polys = segment_polys
        self.allowed: list[float] = [0.0] + _numbers(rows)
        self._n = 0

    def _new(self, ring: list[tuple[float, float]]) -> str:
        self._n += 1
        pid = f"p{self._n}"
        self.polys[pid] = ring_of(Polygon(ring), 0.0)  # always CCW so edge indices match what `measure` shows
        return pid

    def _poly(self, pid: str) -> list[tuple[float, float]]:
        if pid not in self.polys:
            raise KeyError(f"unknown polygon_id {pid!r}; known: {sorted(self.polys)}")
        return self.polys[pid]

    def _seg(self, ids: list[str]) -> list[dict[str, Any]]:
        missing = [i for i in ids if i not in self.rows]
        if missing:
            raise KeyError(f"unknown segment ids {missing}; known: {sorted(self.rows)}")
        return [self.rows[i] for i in ids]

    # --- tools
    def measure(self, polygon_id: str) -> dict[str, Any]:
        m = measure(self._poly(polygon_id))
        return {"polygon_id": polygon_id, "area_sqft": m["area_sqft"], "perimeter_ft": m["perimeter_ft"],
                "bounds": list(m["bounds"]), "min_rotated_rect_ft": m["min_rotated_rect_ft"],
                "edges": [{"index": e["index"], "from": list(e["from"]), "to": list(e["to"]),
                           "length_ft": e["length_ft"], "outward_bearing_deg": e["outward_bearing_deg"]}
                          for e in m["edges"]]}

    def propose_split(self, polygon_id: str, line_ft: list[list[float]]) -> dict[str, Any]:
        parts = split_footprint(self._poly(polygon_id), line_ft)
        out = []
        for part in parts:
            pid = self._new(part["polygon"])
            out.append({"polygon_id": pid, "area_sqft": part["area_sqft"],
                        "bounds": list(Polygon(part["polygon"]).bounds)})
        return {"parts": out}

    def region_from_segments(self, segment_ids: list[str]) -> dict[str, Any]:
        rows = self._seg(segment_ids)
        fp = Polygon(self.footprint)
        shapes = []
        for r in rows:
            sp = self.segment_polys.get(r["id"]) or box(*r["bbox_ft"])
            shapes.append(sp if not r.get("inside_footprint", True) and r.get("form_hint") == "sloped"
                          else sp.intersection(fp))
        union = unary_union([s for s in shapes if not s.is_empty]).buffer(0)
        parts = [p for p in polygons_of(union) if p.area > 1.0]
        ground = sum(r["ground_area_sqft"] for r in rows)
        out = []
        for p in sorted(parts, key=lambda g: -g.area):
            pid = self._new(ring_of(p.simplify(0.1), 0.0))
            out.append({"polygon_id": pid, "area_sqft": p.area, "bounds": list(p.bounds)})
        return {"parts": out, "segments_ground_area_sqft": ground}

    def rect_fit(self, polygon_id: str) -> dict[str, Any]:
        verts, short, long_, area = rect_fit(self._poly(polygon_id))
        pid = self._new(verts)
        return {"polygon_id": pid, "short_side_ft": short, "long_side_ft": long_, "area_sqft": area}

    def pitch_rise_from_segments(self, segment_ids: list[str]) -> dict[str, Any]:
        rows = [r for r in self._seg(segment_ids) if r.get("pitch_rise") is not None]
        w = sum(r["ground_area_sqft"] for r in rows) or 1.0
        mean = sum(r["pitch_rise"] * r["ground_area_sqft"] for r in rows) / w
        vals = [r["pitch_rise"] for r in rows]
        return {"pitch_rise": mean, "min": min(vals), "max": max(vals), "spread": max(vals) - min(vals),
                "n_segments": len(rows)}

    def hip_roof_edges(self, polygon_id: str, pitch_rise: float, gable_edges: list[int] | None = None
                       ) -> dict[str, Any]:
        ring = self._poly(polygon_id)
        res = hip_roof_edges(ring, pitch_rise, set(gable_edges or ()))
        t = res["totals"]
        return {"polygon_id": polygon_id, "form": "gable" if gable_edges else "hip",
                "eave_ft": t["eaves_ft"], "rake_ft": t["rakes_ft"], "ridge_ft": t["ridges_ft"],
                "hip_ft": t["hips_ft"], "valley_ft": t["valleys_ft"], "roof_area_sqft": t["facet_area_sqft"],
                "plan_area_sqft": t["plan_area_sqft"],
                "facets": [{"aspect_deg": f["aspect_deg"], "area_sqft": f["area"]} for f in res["facets"]],
                "notes": res["notes"]}

    def is_known(self, v: float) -> bool:
        return any(abs(v - a) <= NUMBER_TOL for a in self.allowed)

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        require_finite(args)
        fn = getattr(self, name, None)
        if name == "finalize" or fn is None or name.startswith("_"):
            raise KeyError(f"unknown tool {name!r}")
        res = _r(fn(**args))
        self.allowed.extend(_numbers(res))
        return res

    # --- finalize
    def finalize(self, args: dict[str, Any]) -> tuple[list[RoofBlock], list[dict[str, Any]], list[str]]:
        """Validate the decision; returns candidate blocks. Raises ValueError with a fix hint."""
        require_finite(args)
        blocks: list[RoofBlock] = []
        decisions = []
        for i, b in enumerate(args.get("blocks", [])):
            ring = self._poly(b["polygon_id"])
            form = b["form"]
            n = len(ring)
            gable = [int(g) for g in b.get("gable_edges", [])]
            if signed_area(ring) < 0:  # footprint given clockwise: reverse and remap edge indices
                ring = ring[::-1]
                gable = [(n - 2 - g) % n for g in gable]
            if any(g < 0 or g >= n for g in gable):
                raise ValueError(f"block {i}: gable_edges out of range for polygon {b['polygon_id']} ({n} edges)")
            if form == "gable" and len(gable) < 2:
                raise ValueError(f"block {i}: a gable needs at least two gable_edges")
            pitch = b.get("pitch_rise")
            if form != "flat" and (pitch is None or not self.is_known(float(pitch))):
                raise ValueError(f"block {i}: pitch_rise {pitch} was not given by the evidence or a tool; "
                                 "copy it from pitch_rise_from_segments")
            aspect = b.get("aspect_deg")
            if form == "shed" and (aspect is None or not self.is_known(float(aspect))):
                raise ValueError(f"block {i}: a shed needs aspect_deg copied from the evidence azimuth")
            rb = RoofBlock(id="", form=form, polygon=list(ring),
                           pitch_rise=0.0 if form == "flat" else float(pitch), gable_edges=gable if form == "gable" else [],
                           aspect_deg=float(aspect) if aspect is not None and form == "shed" else None,
                           notes=[str(e) for e in b.get("evidence", [])], confidence=b.get("confidence", "medium"))
            geom = block_geometry(form, rb.polygon, rb.pitch_rise, rb.gable_edges, rb.aspect_deg)
            rb.ridge_azimuth_deg = ridge_azimuth(form, rb.polygon, rb.aspect_deg, geom)
            rb.notes.extend(n for n in geom.get("notes", []) if n not in rb.notes)
            blocks.append(rb)
            decisions.append({"polygon_id": b["polygon_id"], "form": form, "pitch_rise": rb.pitch_rise,
                              "gable_edges": rb.gable_edges, "aspect_deg": rb.aspect_deg,
                              "confidence": rb.confidence, "evidence": rb.notes})
        sloped = [Polygon(r.polygon).buffer(0) for r in blocks if r.form != "flat"]
        for i in range(len(sloped)):
            for j in range(i + 1, len(sloped)):
                inter = sloped[i].intersection(sloped[j]).area
                if inter > 0.1 * min(sloped[i].area, sloped[j].area):
                    raise ValueError(f"blocks {i} and {j} overlap by {inter:.0f} sqft; split or fit them again")
        if not blocks:
            raise ValueError("finalize needs at least one block")
        return blocks, decisions, [str(w) for w in args.get("warnings", [])]
