"""Write the plane engine's example envelope (``fixtures/roof_engine/roof_measurement_0.6_engine.json``), deterministically.

``python -m roof_measure.synth_envelopes [fixtures_dir]`` (or ``make fixtures``) rewrites it from the synthetic roof of
``synth_engine_envelope``. The older fixtures in the same folder (the four 0.2 envelopes, the synthetic models, the
planes-only example) are kept as files for the Dart tests that read them; nothing generates them any more.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .model import _round

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
ENGINE_DIR = "roof_engine"
ENGINE_NAME = "roof_measurement_0.6_engine"


def generate_all(out_dir: Path = FIXTURES) -> dict[str, int]:
    """Write the engine example; returns name -> bytes."""
    from .synth_engine_envelope import engine_envelope

    sub = out_dir / ENGINE_DIR  # the plane engine's example: contract-0.6 keys, flat + pitched + a step, a chimney and a lantern
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / f"{ENGINE_NAME}.json"
    path.write_text(json.dumps(_round(engine_envelope()), indent=1) + "\n")
    return {f"{ENGINE_DIR}/{ENGINE_NAME}": path.stat().st_size}


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    for name, size in generate_all(Path(args[0]) if args else FIXTURES).items():
        print(f"{name}.json: {size} bytes")


if __name__ == "__main__":
    main()
