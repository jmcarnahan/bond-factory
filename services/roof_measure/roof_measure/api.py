"""HTTP API for the Flutter demo: ``POST /measure`` and the fixture endpoints.

Run with ``make serve`` (port 8011). Results are cached on disk under ``out/`` keyed by
address and method, so a repeated request for the same building is instant and costs no
agent calls. CORS is open for localhost origins only (the web demo runs on another port).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .cli import METHODS, PipelineError, run_pipeline

log = logging.getLogger(__name__)

SERVICE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = SERVICE_DIR / "out"
FIXTURES_DIR = SERVICE_DIR.parents[1] / "fixtures"

app = FastAPI(title="roof-measure", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"])


class MeasureRequest(BaseModel):
    address: str = Field(max_length=200)
    method: str = "lidar_skeleton"
    blocks_fixture: str | None = None  # NAME of a blocks JSON in fixtures/ (skips the data stages)
    solar_fixture: str | None = None  # NAME of a Solar insights JSON in fixtures/
    no_agent: bool = False
    fixture: str | None = None  # method "fixture": which fixture to return (default site1_lidar)


def _fixture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))


def _fixture_path(name: str | None) -> Path | None:
    """Resolve a fixture NAME strictly under FIXTURES_DIR; 400 for anything else."""
    if name is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not name.endswith(".json") or ".." in name:
        raise HTTPException(400, "fixture names look like 'site1_blocks.json'")
    path = FIXTURES_DIR / name
    if not path.is_file():
        raise HTTPException(400, f"no fixture {name!r} in fixtures/")
    return path


def _safe_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise HTTPException(400, "bad fixture name")
    return name


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/fixtures")
def list_fixtures() -> list[dict[str, Any]]:
    """Roof-model fixtures (schema bond.roof_model/0.1) in the repository's ``fixtures/`` directory.

    Service inputs that live beside them (blocks files, Solar responses) are not listed, so a
    client can render every entry.
    """
    out = []
    for p in sorted(FIXTURES_DIR.glob("*.json")):
        try:
            if json.loads(p.read_text()).get("schema") != "bond.roof_model/0.1":
                continue
        except (ValueError, AttributeError):
            continue
        out.append({"name": p.stem, "file": p.name, "bytes": p.stat().st_size})
    return out


@app.get("/fixtures/{name}")
def get_fixture(name: str) -> Any:
    path = FIXTURES_DIR / f"{_safe_name(name)}.json"
    if not path.is_file():
        raise HTTPException(404, f"no fixture {name!r}; have {_fixture_names()}")
    return json.loads(path.read_text())


@app.post("/measure")
def measure(req: MeasureRequest) -> Any:
    """Roof model JSON for an address (cached). ``method: "fixture"`` returns a saved fixture."""
    if req.method == "fixture":
        return get_fixture(req.fixture or "site1_lidar")
    if req.method not in METHODS:
        raise HTTPException(400, f"method must be one of {METHODS + ('fixture',)}")
    blocks_path = _fixture_path(req.blocks_fixture)
    solar_path = _fixture_path(req.solar_fixture)
    key = hashlib.sha256(json.dumps([req.address.strip().lower(), req.method, req.blocks_fixture,
                                     req.solar_fixture, req.no_agent]).encode()).hexdigest()[:16]
    cache = OUT_DIR / f"api_{key}.json"
    if cache.is_file():
        return json.loads(cache.read_text())
    try:
        res = run_pipeline(req.address, OUT_DIR, req.method, blocks_path=blocks_path,
                           solar_fixture=solar_path, no_agent=req.no_agent)
    except PipelineError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # data-layer errors carry human messages (GeocodeError, FootprintError, ...)
        log.exception("measure failed")
        raise HTTPException(502, "The measurement failed upstream; see the service log.") from exc
    cache.write_text(json.dumps(res.model))
    return res.model
