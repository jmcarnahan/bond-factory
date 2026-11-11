"""Command line and the pipeline behind it: address -> footprint -> evidence -> model JSON + PNG.

``roof-measure measure "<address>" --out out/`` runs the data stages (geocode, footprint,
LiDAR blocks) then the model stages. ``--blocks file.json`` skips the data stages and uses a
saved ``bond.roof_blocks`` file, so the model layer runs with no network.

The data-layer modules are imported lazily inside the stages: the CLI works with ``--blocks``
even if they are broken or missing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from .model import ModelError
from .pipeline import PipelineError, PipelineResult, run_pipeline  # noqa: F401  (re-exported)
from .text import ft_in

log = logging.getLogger(__name__)

METHODS = ("lidar_skeleton", "lidar_agent", "solar_agent")
DATA_ERRORS = {"GeocodeError", "FootprintError", "AmbiguousBuilding", "LidarError", "LidarTooSparse",
               "SolarUnavailable", "BlocksError", "ModelError", "DeadlineExceeded"}


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
    m.add_argument("--method", choices=(*METHODS, "auto"), default="lidar_skeleton",
                   help="lidar_skeleton: rules on LiDAR blocks; lidar_agent / solar_agent: Claude decides the forms "
                        "(needs ANTHROPIC_API_KEY unless --no-agent)")
    m.add_argument("--blocks", help="saved bond.roof_blocks JSON: skip the data stages")
    m.add_argument("--solar-fixture", help="saved/synthetic buildingInsights JSON instead of the live Solar API")
    m.add_argument("--no-agent", action="store_true", help="deterministic rules instead of the Claude agent")
    m.add_argument("--max-rounds", type=int, default=12, help="agent tool rounds (hard cap 12)")
    m.add_argument("--merge-flats", action="store_true",
                   help="merge touching flat blocks of similar level (default: keep separate, internal eaves)")
    m.add_argument("--verify", action="store_true", help="run the verifier (deterministic merge; LLM review with a key)")
    m.add_argument("-v", "--verbose", action="store_true", help="log stage details to stderr")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        res = run_pipeline(a.address, a.out, a.method, blocks_path=a.blocks, solar_fixture=a.solar_fixture,
                           no_agent=a.no_agent, max_rounds=min(a.max_rounds, 12),
                           merge_flats=a.merge_flats, verify=a.verify)
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
