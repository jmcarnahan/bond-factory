"""Harness engine command: ``python -m roof_measure.engine.cli <house_dir> <out_json> [--params '{json}']``.

Reads a roof-eval house folder (see ``load``), measures it and writes the harness result JSON (no wall time, so two
runs are byte-identical). Exit 0 also for a refusal (the verdict is in the JSON); non-zero only on a failure.
``--model PATH`` also writes what the adapter makes of the result: ``{"model", "assessment"}`` (the validated roof
model in feet and the contract-0.4 quality, planes and totals), for a look at the envelope without the pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roof_measure.engine.cli")
    ap.add_argument("house_dir")
    ap.add_argument("out_json")
    ap.add_argument("--params", default="", help="JSON object of EngineParams fields to override")
    ap.add_argument("--timeout", type=float, default=0.0, help="seconds; 0 = no deadline")
    ap.add_argument("--model", default="", help="also write the adapted roof model + assessment to this path")
    args = ap.parse_args(argv)

    from . import measure_roof
    from .errors import EngineError
    from .load import load_house
    from .params import DEFAULT

    params = DEFAULT.replace(**json.loads(args.params)) if args.params else DEFAULT
    house = load_house(args.house_dir)
    deadline = time.monotonic() + args.timeout if args.timeout > 0 else None
    try:
        res = measure_roof(house.points, house.footprint, params=params, deadline=deadline,
                           outline_source=str(house.meta.get("outline_source") or ""),
                           parcel_match=house.meta.get("parcel_match"), context=house.wide)
    except EngineError as ex:
        print(f"engine error: {type(ex).__name__}: {ex}", file=sys.stderr)
        return 2
    with open(args.out_json, "w") as fh:
        json.dump(res.to_result_json(house.slug), fh, indent=1)
    if args.model and not res.refused:
        return _write_model(args.model, res, house, params)
    return 0


def _write_model(path: str, res, house, params) -> int:
    """The adapted model (validated) and assessment; exit 3 when the result cannot be a valid model."""
    from ..blockset import BlockSet
    from ..model import ModelError
    from ..quality import assess_engine
    from .adapter import engine_model

    ground = float(house.points.ground_z)
    base = BlockSet(address={"formatted": house.slug}, origin={"lat": 0.0, "lng": 0.0}, frame={}, footprint_ft=[],
                    footprint_meta={"provider": str(house.meta.get("outline_source") or ""), "id": house.slug,
                                    "area_sqft": house.footprint.area / 0.09290304})
    try:
        model = engine_model(res, base, ground, params=params)
    except ModelError as ex:
        print(f"model error: {ex}", file=sys.stderr)
        return 3
    with open(path, "w") as fh:
        json.dump({"model": model, "assessment": assess_engine(res, model)}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
