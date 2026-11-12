"""HTTP routing for the roof measurement service (contract: docs/contract-0.2.md).

Routes only: validation here, work in ``service.py`` and ``runner.py``. Run with
``uvicorn roof_measure.api:app --host :: --port $PORT``. The app is built on first access, so a missing
``ROOF_MEASURE_TOKEN`` stops the process at start-up instead of serving unauthenticated.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth
from .errors import error_body
from .fixtures import fixture_path
from .jobs import QueueFull
from .service import RunFn, Service
from .settings import Settings
from .version import PIPELINE_VERSION

LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"
log = logging.getLogger("roof_measure.api")
Method = Literal["auto", "lidar_skeleton", "lidar_agent", "solar_agent"]
DEBUG_FIELDS = ("blocks_fixture", "solar_fixture", "fixture")
MAX_BODY_BYTES = 8192  # a request is about 300 bytes; checked after reading
MAX_CONTENT_LENGTH = 65536  # refused from the header, before the body is read


class MeasureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)  # "34", true, "yes", 1 are not coordinates or flags
    address: str = Field(min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    method: Method | Literal["fixture"] = "auto"
    verify: bool = True
    force: bool = False
    blocks_fixture: str | None = None  # debug only: NAME of a blocks JSON in fixtures/
    solar_fixture: str | None = None  # debug only: NAME of a Solar insights JSON in fixtures/
    fixture: str | None = None  # debug only, method "fixture": NAME of the fixture to return

    @field_validator("address")
    @classmethod
    def _address_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("address must not be blank")
        return v

    @field_validator("blocks_fixture", "solar_fixture", "fixture")
    @classmethod
    def _bare_name(cls, v: str | None) -> str | None:
        """Accept ``site1_blocks`` as well as ``site1_blocks.json`` (the safe-name check runs on the result)."""
        return v if v is None or v.endswith(".json") else v + ".json"

    @model_validator(mode="after")
    def _both_or_neither(self) -> MeasureRequest:
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat requires lng and lng requires lat")
        return self


def _err(status: int, code: str, message: str | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message), status_code=status, headers=headers)


def _invalid(errors: list[Any]) -> JSONResponse:
    """422 naming the first bad field and rule, never echoing the input."""
    first = errors[0] if errors else {}
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    kind = str(first.get("type", "invalid"))
    if kind == "value_error":  # our own validators: their text names the fields ("lat and lng must be given together")
        reason = str(first.get("msg", "")).removeprefix("Value error, ")
        return _err(422, "invalid_request", f"Invalid request: {reason}." if not where else
                    f"Invalid request: {where}: {reason}.")
    hint = {"missing": "is required", "extra_forbidden": "is not a known field", "float_type": "must be a number",
            "bool_type": "must be true or false", "string_type": "must be a string",
            "greater_than_equal": "is below the allowed range", "less_than_equal": "is above the allowed range",
            "string_too_long": "is too long", "string_too_short": "must not be empty",
            "json_invalid": "is not valid JSON"}.get(kind, f"is invalid ({kind})")
    return _err(422, "invalid_request", f"Invalid request: {where or 'body'} {hint}.")


def create_app(settings: Settings | None = None, *, token: str | None = None, run: RunFn | None = None,
               env: dict[str, str] | None = None) -> FastAPI:
    """Build the app. ``token`` None means: derive from the environment (``auth.require_token``)."""
    settings = settings or Settings.from_env(env)
    enforce = auth.require_token(env) if token is None else token
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)  # no-op when the host already configured logging
    service = Service(settings, run)
    log.info("roof-measure %s starting: bind_host=%s auth=%s debug=%s", PIPELINE_VERSION,
             (env or os.environ).get("ROOF_MEASURE_HOST", "::"), "on" if enforce else "off", settings.debug)
    docs = {} if settings.debug else {"docs_url": None, "redoc_url": None, "openapi_url": None}  # schema lists debug fields
    app = FastAPI(title="roof-measure", version=PIPELINE_VERSION, **docs)
    app.state.service = service
    auth.install(app, enforce)
    app.add_middleware(CORSMiddleware, allow_origin_regex=settings.cors_regex, allow_methods=["*"],
                       allow_headers=["*"])

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _invalid(list(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _err(404, "unknown_job", "No such resource.")
        return _err(exc.status_code, "invalid_request", "The request cannot be served.")

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled %s in a request handler", type(exc).__name__)
        log.debug("unhandled detail", exc_info=exc)
        return _err(500, "measurement_failed", "The service hit an unexpected error.")

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        """No disk, no network. ``abandoned_workers`` counts workers held by jobs the watchdog gave up on."""
        return {"status": "ok", "pipeline_version": PIPELINE_VERSION,
                "abandoned_workers": service.runner.abandoned_workers}

    @app.post("/v1/measurements", status_code=202)
    async def create_measurement(request: Request) -> JSONResponse:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_CONTENT_LENGTH:
            return _err(422, "invalid_request", "Request body too large.")
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return _err(422, "invalid_request", "Request body too large.")
        try:
            req = MeasureRequest.model_validate_json(raw)
        except ValidationError as exc:
            return _invalid(list(exc.errors()))
        body = req.model_dump()
        if not settings.debug and (req.method == "fixture" or any(body[k] for k in DEBUG_FIELDS)):
            return _err(422, "invalid_request", "Fixture inputs are available only with ROOF_MEASURE_DEBUG=1.")
        try:
            for k in ("blocks_fixture", "solar_fixture", "fixture"):
                fixture_path(settings, body[k])
        except ValueError as exc:
            return _err(422, "invalid_request", str(exc))
        try:
            job = service.submit(body)
        except QueueFull:
            return _err(429, "queue_full", headers={"Retry-After": "30"})
        return JSONResponse({"id": job["id"], "status": job["status"]}, status_code=202)

    @app.get("/v1/measurements/{job_id}")
    def get_measurement(job_id: str) -> JSONResponse:
        view = service.view(job_id)
        if view is None:
            return _err(404, "unknown_job")
        return JSONResponse(view)

    if settings.debug:
        _debug_routes(app, settings)
    return app


def _debug_routes(app: FastAPI, settings: Settings) -> None:
    def is_roof(doc: Any) -> bool:
        return isinstance(doc, dict) and (str(doc.get("schema", "")).startswith("bond.roof_model/0.")
                                          or str(doc.get("contract", "")).startswith("bond.roof_model/0."))

    @app.get("/fixtures")
    def list_fixtures() -> list[dict[str, Any]]:
        out = []
        for p in sorted(settings.fixtures_dir.glob("*.json")):
            try:
                doc = json.loads(p.read_text())
            except ValueError:
                continue
            if is_roof(doc):
                out.append({"name": p.stem, "file": p.name, "bytes": p.stat().st_size,
                            "kind": "envelope" if "contract" in doc else "model"})
        return out

    @app.get("/fixtures/{name}")
    def get_fixture(name: str) -> Any:
        if not re.fullmatch(r"[A-Za-z0-9_\-.]+", name) or ".." in name:
            return _err(404, "unknown_job", "No such fixture.")
        path = settings.fixtures_dir / f"{name}.json"
        if not path.is_file():
            return _err(404, "unknown_job", "No such fixture.")
        return json.loads(path.read_text())


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """``roof_measure.api:app`` for uvicorn: built from the environment on first access."""
    global _app
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        try:
            _app = create_app()
        except auth.AuthConfigError as exc:  # one line and exit 1, not a traceback, when started misconfigured
            print(f"roof-measure: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
    return _app
