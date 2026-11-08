"""Command line and the pipeline behind it: address -> footprint -> evidence -> model JSON + PNG.

``roof-measure measure "<address>" --out out/`` runs the data stages (geocode, footprint,
LiDAR blocks) then the model stages. ``--blocks file.json`` skips the data stages and uses a
saved ``bond.roof_blocks`` file, so the model layer runs with no network.

The data-layer modules are imported lazily inside the stages: the CLI works with ``--blocks``
even if they are broken or missing.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .classify import BlockSet, Classification, RoofBlock, classify_blocks
from .model import ModelError, build_model, write_model
from .render import ft_in, render_png, slug

log = logging.getLogger(__name__)

METHODS = ("lidar_skeleton", "lidar_agent", "solar_agent")
SOLAR_KEY_ENV = ("GOOGLE_SOLAR_API_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY")


DATA_ERRORS = {"GeocodeError", "FootprintError", "LidarError", "LidarTooSparse", "SolarUnavailable", "BlocksError",
               "ModelError"}


class PipelineError(RuntimeError):
    """A stage failed in a way the user can act on (message is for humans)."""


@dataclass
class PipelineResult:
    model: dict[str, Any]
    blockset: BlockSet
    paths: dict[str, Path] = field(default_factory=dict)
    agent_transcript: dict[str, Any] | None = None


# ----------------------------------------------------------------------------- data stages
def _stage_footprint(address: str) -> BlockSet:
    """Geocode + footprint -> an empty block set (footprint only)."""
    import numpy as np
    from shapely.geometry import Polygon

    from . import footprint as fp_mod
    from . import frame as frame_mod
    from . import geocode

    g = geocode.geocode(address)
    fp = fp_mod.fetch_footprint(g.lat, g.lng, g.parts)
    frame, fp_m = frame_mod.Frame.for_footprint(fp.polygon_wgs84)
    ring = [tuple(p) for p in frame.to_ft(np.array(fp_m.exterior.coords))][:-1]
    poly = Polygon(ring)
    if not poly.exterior.is_ccw:
        ring = ring[::-1]
    bs = BlockSet(
        address={"line1": g.parts.line1, "city": g.parts.city, "state": g.parts.state, "zip": g.parts.zip,
                 "formatted": g.formatted},
        origin={"lat": frame.origin_lat, "lng": frame.origin_lng},
        frame={"epsg": frame.epsg, "x0_m": frame.x0_m, "y0_m": frame.y0_m},
        footprint_ft=ring,
        footprint_meta={"provider": fp.provider, "id": fp.id, "area_sqft": fp.area_sqft, "height_ft": fp.height_ft})
    bs.extra["_geo"] = {"lat": g.lat, "lng": g.lng}
    return bs


def _stage_blocks(address: str, out_dir: Path, tag: str) -> BlockSet:
    """Full data stage for the LiDAR methods; svc-data writes the blocks JSON, we read it back."""
    from . import blocks as blocks_mod
    from . import footprint as fp_mod
    from . import frame as frame_mod
    from . import geocode, lidar

    g = geocode.geocode(address)
    fp = fp_mod.fetch_footprint(g.lat, g.lng, g.parts)
    frame, fp_m = frame_mod.Frame.for_footprint(fp.polygon_wgs84)
    points = lidar.fetch_for_footprint(fp_m, frame.epsg)
    address_d = {"line1": g.parts.line1, "city": g.parts.city, "state": g.parts.state, "zip": g.parts.zip,
                 "formatted": g.formatted}
    meta = {"provider": fp.provider, "id": fp.id, "area_sqft": fp.area_sqft, "height_ft": fp.height_ft}
    blockset = blocks_mod.segment_blocks(points, fp_m, frame, address=address_d, footprint_meta=meta)
    path = out_dir / f"{tag}_blocks.json"
    blockset.to_json(path)
    return BlockSet.load(path)


def _solar_key() -> str:
    for name in SOLAR_KEY_ENV:
        if os.environ.get(name):
            return os.environ[name]
    raise PipelineError("The live Solar API needs a key in GOOGLE_SOLAR_API_KEY (and the API enabled on the "
                        "project). Use --solar-fixture for the synthetic fixture.")


# ----------------------------------------------------------------------------- pipeline
def run_pipeline(address: str, out_dir: str | Path, method: str = "lidar_skeleton", *,
                 blocks_path: str | Path | None = None, solar_fixture: str | Path | None = None,
                 no_agent: bool = False, max_rounds: int = 12, merge_flats: bool = False,
                 client: Any | None = None) -> PipelineResult:
    """Run the whole pipeline for one address and write ``<slug>_{blocks,model}.json`` and ``.png``."""
    from . import agent as agent_mod
    from . import solar

    if method not in METHODS:
        raise PipelineError(f"method must be one of {METHODS}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = slug(address)
    kw = {"merge_flats": merge_flats}

    # 1. data stages
    if blocks_path:
        base = BlockSet.load(blocks_path)
    elif method == "solar_agent":
        base = _stage_footprint(address)
    else:
        base = _stage_blocks(address, out, tag)
    if not base.address.get("formatted"):
        base.address = {"line1": address, "city": "", "state": "", "zip": "", "formatted": address}

    # 2. model stages
    transcript: dict[str, Any] | None = None
    source: dict[str, Any] = {"method": method}
    model_blockset = base
    classification: Classification
    roof_blocks: list[RoofBlock]
    if method == "solar_agent":
        if solar_fixture:
            insights, live = solar.load_fixture(solar_fixture), False
        else:
            ll = base.extra.get("_geo") or base.origin
            try:
                insights, live = solar.fetch_building_insights(ll.get("lat"), ll.get("lng"), _solar_key()), True
            except solar.SolarUnavailable as exc:
                raise PipelineError(str(exc)) from exc
        evidence = solar.segments_to_evidence(insights, base.frame, base.footprint_ft)
        meta = solar.insights_meta(insights, live)
        source["solar"] = meta
        if insights.get("_SYNTHETIC"):
            source["warnings"] = ["Solar input is the SYNTHETIC fixture, not a Google response."]
        model_blockset = solar.evidence_to_blockset(evidence, base)
        if no_agent:
            classification = classify_blocks(model_blockset, **kw)
            classification.notes.append("Deterministic path (no agent): segment boxes classified by rules.")
        else:
            res = _run_agent(agent_mod, base, evidence, "solar", client, max_rounds, meta)
            classification = Classification(blocks=res.blocks, notes=res.notes + agent_mod.agent_notes(res),
                                            warnings=res.warnings, gap_filled_pct=res.filled_pct)
            transcript = _transcript(res)
            source["agent"] = {"model": res.model, "api_calls": res.api_calls}
        roof_blocks = classification.blocks
    elif method == "lidar_agent" and not no_agent:
        res = _run_agent(agent_mod, base, None, "lidar", client, max_rounds, None)
        classification = Classification(blocks=res.blocks, notes=res.notes + agent_mod.agent_notes(res),
                                        warnings=res.warnings, gap_filled_pct=res.filled_pct)
        roof_blocks = res.blocks
        transcript = _transcript(res)
        source["agent"] = {"model": res.model, "api_calls": res.api_calls}
    else:
        classification = classify_blocks(base, **kw)
        roof_blocks = classification.blocks
        if method == "lidar_agent":
            classification.notes.append("Deterministic path (no agent): LiDAR blocks classified by rules.")
    model = build_model(model_blockset, roof_blocks, source, classification)

    # 3. outputs
    paths = {"blocks": out / f"{tag}_blocks.json", "model": out / f"{tag}_model.json",
             "png": out / f"{tag}_model.png"}
    base.extra.pop("_geo", None)
    base.save(paths["blocks"])
    model["debug"]["png"] = paths["png"].name
    write_model(model, paths["model"])
    render_png(model, paths["png"])
    if transcript is not None:
        paths["transcript"] = out / "agent_transcript.json"
        paths["transcript"].write_text(json.dumps(transcript, indent=1, default=str))
    return PipelineResult(model=model, blockset=base, paths=paths, agent_transcript=transcript)


def _run_agent(agent_mod: Any, base: BlockSet, evidence: list[dict[str, Any]] | None, kind: str,
               client: Any | None, max_rounds: int, imagery: dict[str, Any] | None) -> Any:
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        raise PipelineError("The agent needs ANTHROPIC_API_KEY in the environment. Pass --no-agent for the "
                            "deterministic path.")
    try:
        return agent_mod.run_agent(base, evidence, kind=kind, client=client, max_rounds=max_rounds, imagery=imagery)
    except agent_mod.AgentError as exc:
        raise PipelineError(f"The agent failed: {exc}. Re-run with --no-agent for the deterministic path.") from exc


def _transcript(res: Any) -> dict[str, Any]:
    return {"model": res.model, "api_calls": res.api_calls, "usage": res.usage, "decisions": res.decisions,
            "filled_pct": res.filled_pct, "messages": res.transcript}


# ----------------------------------------------------------------------------- printing
def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split())


def totals_table(model: dict[str, Any]) -> str:
    """Plain text table of the headline numbers and the ten lengths."""
    t = model["totals"]
    rows = [("Total area", f"{t['total_area_sqft']:,.0f} sq ft  ({t['squares']:.2f} squares)"),
            ("Pitched area", f"{t['pitched_area_sqft']:,.0f} sq ft"),
            ("Flat area", f"{t['flat_area_sqft']:,.0f} sq ft"),
            ("Predominant pitch", f"{t['predominant_pitch_rise']:.1f}/12  ({t['predominant_pitch_area_sqft']:,.0f} sq ft)")]
    rows += [(k.replace("_", " ").capitalize(), f"{ft_in(v)}  ({v:,.1f} ft)") for k, v in t["lengths_ft"].items()]
    w = max(len(r[0]) for r in rows)
    lines = [(f"{model['address'].get('formatted', '')}   method={model['source']['method']}   "
             f"confidence={model['confidence']['overall']}")]
    lines += [f"  {k:<{w}}  {v}" for k, v in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roof-measure", description="Address -> roof measurement model (POC).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="measure one address")
    m.add_argument("address", help='one-line US address, quoted, e.g. "100 Example Ave, Sampletown, CA 90000"')
    m.add_argument("--out", default="out", help="output directory (default out/)")
    m.add_argument("--method", choices=METHODS, default="lidar_skeleton",
                   help="lidar_skeleton: rules on LiDAR blocks; lidar_agent / solar_agent: Claude decides the forms "
                        "(needs ANTHROPIC_API_KEY unless --no-agent)")
    m.add_argument("--blocks", help="saved bond.roof_blocks JSON: skip the data stages")
    m.add_argument("--solar-fixture", help="saved/synthetic buildingInsights JSON instead of the live Solar API")
    m.add_argument("--no-agent", action="store_true", help="deterministic rules instead of the Claude agent")
    m.add_argument("--max-rounds", type=int, default=12, help="agent tool rounds (hard cap 12)")
    m.add_argument("--merge-flats", action="store_true",
                   help="merge touching flat blocks of similar level (default: keep separate, internal eaves)")
    m.add_argument("-v", "--verbose", action="store_true", help="log stage details to stderr")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        res = run_pipeline(a.address, a.out, a.method, blocks_path=a.blocks, solar_fixture=a.solar_fixture,
                           no_agent=a.no_agent, max_rounds=min(a.max_rounds, 12),
                           merge_flats=a.merge_flats)
    except PipelineError as exc:
        print(f"error: {_one_line(exc)}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Data-layer errors carry human messages; matched by name so a missing class cannot break import.
        if type(exc).__name__ in DATA_ERRORS or isinstance(exc, (ModelError, requests.RequestException)):
            print(f"error: {type(exc).__name__}: {_one_line(exc)}", file=sys.stderr)
            return 2
        raise
    print(totals_table(res.model))
    for k, p in res.paths.items():
        print(f"wrote {k}: {p}")
    for w in res.model["warnings"]:
        print(f"warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
