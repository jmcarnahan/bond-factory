"""Emit the synthetic fixtures and the four ``bond.roof_model/0.2`` envelopes, deterministically.

``python -m roof_measure.synth_envelopes [fixtures_dir]`` (or ``make fixtures``) rewrites
``roof_measurement_0.2_{pass,adjusted,unverified,fail}.json``, ``synthetic_flat_curbs.json``,
``synthetic_hip_zigzag.json`` and ``synthetic_solar_response.json``.

The ``verification`` block of ``pass``, ``adjusted`` and ``unverified`` is what ``verify.verify`` emits: the
LLM turns come from a scripted fake client (no network, no key) and ``unverified`` runs with the key removed.
Only ``fail`` is composed by hand, because real code never produces a fail on the synthetic hip.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .envelope import build_envelope, totals_from_model
from .model import build_model
from .synth import FIXTURES, synthetic_gable, synthetic_hip
from .synth_extra import (
    labelled,
    synthetic_flat_curbs,
    synthetic_hip_zigzag,
    synthetic_solar_response,
    write_json,
    write_raw,
)
from .verify import verify

OSM_WARNING = "Footprint from OpenStreetMap; parcel data unavailable outside Los Angeles County."
LLM = "claude-sonnet-5-5"


class ScriptedClient:
    """Plays one scripted assistant turn: ``finalize_verdict`` with the given verdict (usage is a fixed example)."""

    def __init__(self, verdict: str, note: str):
        self.messages = SimpleNamespace(create=self._create)
        self.verdict, self.note, self.calls = verdict, note, 0

    def _create(self, **_kw: Any) -> Any:
        self.calls += 1
        block = SimpleNamespace(type="tool_use", id="t1", name="finalize_verdict",
                                input={"verdict": self.verdict, "notes": [self.note], "adjustments": []})
        return SimpleNamespace(content=[block], usage=SimpleNamespace(input_tokens=8200, output_tokens=310))


@contextlib.contextmanager
def _without_key() -> Iterator[None]:
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def _verified(model: dict[str, Any], verdict: str, note: str) -> Any:
    return verify(model, client=ScriptedClient(verdict, note))


def _base(fn) -> dict[str, Any]:
    bs, rbs = fn()
    return labelled(build_model(bs, rbs, {"method": "fixture"}))


def envelopes() -> dict[str, dict[str, Any]]:
    base = {"method_used": "lidar_skeleton", "generated_at": "2026-11-10T00:00:00Z"}
    osm = {"footprint_source": "osm", "warnings": [OSM_WARNING], "warning_codes": ["footprint_osm"]}

    pass_res = _verified(_base(synthetic_hip), "pass", "Synthetic example: edge lengths and areas agree.")
    pass_env = build_envelope(pass_res.model, verification=pass_res.verification, **base, **osm)

    adj_res = _verified(synthetic_hip_zigzag(), "adjusted", "Merged the nearly collinear south eave segments.")
    adj_env = build_envelope(
        adj_res.model, verification=adj_res.verification, **base, footprint_source="osm",
        warnings=[OSM_WARNING, "The verifier merged short eave segments and recomputed the totals."],
        warning_codes=["footprint_osm", "verifier_adjusted"])

    with _without_key():
        unv_res = verify(_base(synthetic_gable))
    unv_env = build_envelope(
        unv_res.model, verification=unv_res.verification, **base, footprint_source="lariac",
        warnings=["Verification was skipped: no verifier key is configured."], warning_codes=["verifier_unverified"])

    fail_m = _base(synthetic_hip)
    orig = dict(totals_from_model(fail_m))
    orig["area_sqft"] = round(orig["area_sqft"] * 1.08, 3)
    orig["squares"] = round(orig["area_sqft"] / 100.0, 3)
    fail_ver = {"verdict": "fail", "adjustments": [], "original_totals": orig, "model": LLM, "rounds": 2,
                "usage": {"input_tokens": 8200, "output_tokens": 310},
                "notes": ["SYNTHETIC FIXTURE: original_totals.area_sqft is forced 8% above the model so the fail "
                          + "rule trips; this is not a real measurement."]}
    fail_env = build_envelope(
        fail_m, verification=fail_ver, **base, footprint_source="osm",
        warnings=[OSM_WARNING, "The verifier found the measurement inconsistent: total area moved more than 5%."],
        warning_codes=["footprint_osm", "verifier_failed"])
    return {"roof_measurement_0.2_pass": pass_env, "roof_measurement_0.2_adjusted": adj_env,
            "roof_measurement_0.2_unverified": unv_env, "roof_measurement_0.2_fail": fail_env}


def generate_all(out_dir: Path = FIXTURES) -> dict[str, int]:
    """Write every fixture this module owns; returns name -> bytes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = {"synthetic_flat_curbs": synthetic_flat_curbs(), "synthetic_hip_zigzag": synthetic_hip_zigzag(),
            "synthetic_solar_response": synthetic_solar_response(), **envelopes()}
    sizes = {}
    for name, doc in docs.items():
        (write_raw if name == "synthetic_solar_response" else write_json)(out_dir / f"{name}.json", doc)
        sizes[name] = (out_dir / f"{name}.json").stat().st_size
    return sizes


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    for name, size in generate_all(Path(args[0]) if args else FIXTURES).items():
        print(f"{name}.json: {size} bytes")


if __name__ == "__main__":
    main()
