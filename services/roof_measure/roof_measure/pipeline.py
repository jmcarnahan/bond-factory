"""The measuring pipeline: address -> footprint -> evidence -> model -> verifier -> 0.2 envelope.

``run_pipeline`` is synchronous. The job service passes a ``Deadline`` (every stage checks it), ``lat_lng``
(skips the geocoder), ``on_stage`` (progress for the job status) and ``verify``. The data-layer modules are
imported lazily inside the stages so ``--blocks`` runs even if they are broken or missing.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely.errors import ShapelyError

from . import agent_pick, cache, config, planes_model, planes_only
from .classify import BlockSet, Classification, RoofBlock, classify_blocks
from .deadline import Deadline, DeadlineExceeded
from .envelope import TOTALS_KEYS, build_envelope, cap_verification, totals_from_model
from .model import build_model, write_model
from .pipeline_notes import collect_warnings
from .pipeline_stages import (  # noqa: F401
    SOLAR_KEY_ENV,
    PipelineError,
    _solar_key,
    _stage_blocks,
    _stage_footprint,
    parse_address,
)
from .text import slug

log = logging.getLogger("roof_measure.pipeline")

METHODS = ("lidar_skeleton", "lidar_agent", "solar_agent")
FALLBACK_ERRORS = ("LidarError", "LidarTooSparse")  # class names: no_lidar_coverage / lidar_too_sparse
AGENT_METHODS = ("lidar_agent", "solar_agent")
AGENT_BUDGET_SHARE = 0.6  # of the time left, so a stuck agent leaves time for the rule result
AGENT_FELL_BACK = "agent_failed_fell_back"


@dataclass
class PipelineResult:
    model: dict[str, Any]
    blockset: BlockSet
    paths: dict[str, Path] = field(default_factory=dict)
    agent_transcript: dict[str, Any] | None = None
    method_used: str = "lidar_skeleton"
    footprint_source: str = "unknown"
    verification: dict[str, Any] = field(default_factory=dict)
    envelope: dict[str, Any] = field(default_factory=dict)
    density_pts_m2: float | None = None
    transient: bool = False  # produced by an outage fall-through: the caller must not cache it


def _noop(_stage: str) -> None:
    return None


def render_png(model: dict[str, Any], path: str | Path) -> Path:
    """The debug picture; imported on use because it needs the ``render`` extra (matplotlib)."""
    from . import render as render_mod

    return render_mod.render_png(model, path)


def _no_verification(model: dict[str, Any], note: str) -> dict[str, Any]:
    return {"verdict": "unverified", "notes": [note], "adjustments": [], "original_totals": totals_from_model(model),
            "model": None, "rounds": 0, "usage": {"input_tokens": 0, "output_tokens": 0}}


def _verify(model: dict[str, Any], enabled: bool, client: Any, deadline: Deadline,
            on_stage: Callable[[str], None]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """(final model, verification block, transcript). The verifier never fails a job (plan D1)."""
    if not enabled:
        return model, _no_verification(model, "Verification was not requested."), []
    on_stage("verify")
    try:
        from .verify import verify

        res = verify(model, client=client, deadline=deadline)
        return res.model, res.verification, list(getattr(res, "transcript", None) or [])
    except Exception as exc:
        log.warning("verifier raised %s; keeping the deterministic model", type(exc).__name__, exc_info=True)
        return model, _no_verification(model, f"Verification could not run ({type(exc).__name__})."), []


# ----------------------------------------------------------------------------- pipeline
def run_pipeline(address: str, out_dir: str | Path, method: str = "lidar_skeleton", *,
                 blocks_path: str | Path | None = None, solar_fixture: str | Path | None = None,
                 no_agent: bool = False, max_rounds: int = 12, merge_flats: bool = False,
                 client: Any | None = None, deadline: Deadline | None = None,
                 lat_lng: tuple[float, float] | None = None, on_stage: Callable[[str], None] | None = None,
                 verify: bool = True, render: bool = True,
                 include_other_buildings: bool = False) -> PipelineResult:
    """Run the whole pipeline for one address; writes ``<slug>_{blocks,model}.json`` and ``.png`` into ``out_dir``.

    ``method="auto"`` is D12: ``lidar_skeleton``, falling back to ``solar_agent`` when LiDAR is missing or too
    thin and both the Solar and Anthropic keys are set (the envelope then carries ``method_fallback``).
    """
    if method == "auto":
        res = _run_auto(address, out_dir, blocks_path=blocks_path, solar_fixture=solar_fixture, no_agent=no_agent,
                        max_rounds=max_rounds, merge_flats=merge_flats, client=client, deadline=deadline,
                        lat_lng=lat_lng, on_stage=on_stage, verify=verify, render=render)
    else:
        if method not in METHODS:
            raise PipelineError(f"method must be one of {METHODS + ('auto',)}")
        res = _run(address, out_dir, method, blocks_path=blocks_path, solar_fixture=solar_fixture, no_agent=no_agent,
                   max_rounds=max_rounds, merge_flats=merge_flats, client=client, deadline=deadline, lat_lng=lat_lng,
                   on_stage=on_stage or _noop, verify=verify, render=render, fallback_from=None)
    if include_other_buildings:  # lot.py: the other buildings on the parcel, measured by the rules (additive keys)
        from .lot import add_other_buildings

        add_other_buildings(res, address=address, lat_lng=lat_lng, deadline=deadline, out_dir=out_dir,
                            blocks_path=blocks_path)
    return res


def _run_auto(address: str, out_dir: str | Path, *, on_stage: Callable[[str], None] | None, **kw: Any) -> PipelineResult:
    stage = on_stage or _noop
    try:
        return _run(address, out_dir, "lidar_skeleton", on_stage=stage, fallback_from=None, **kw)
    except Exception as exc:
        has_keys = bool(config.anthropic_key() or kw.get("client")) and bool(config.solar_key())
        if type(exc).__name__ not in FALLBACK_ERRORS or not has_keys:
            raise
        log.info("auto: LiDAR failed (%s); falling back to solar_agent", type(exc).__name__)
        try:
            return _run(address, out_dir, "solar_agent", on_stage=stage, fallback_from="lidar_skeleton", **kw)
        except Exception as fallback_exc:
            # the LiDAR failure is the answer (it carries the density); say the fallback was tried too
            exc.add_note(f"The solar_agent fallback also failed ({type(fallback_exc).__name__}).")
            raise exc from fallback_exc


def _run(address: str, out_dir: str | Path, method: str, **kw: Any) -> PipelineResult:
    """``_run_inner`` with every HTTP fetch bound to the job's deadline (``cache.deadline_scope``)."""
    with cache.deadline_scope(kw.get("deadline")):
        return _run_inner(address, out_dir, method, **kw)


def _run_inner(address: str, out_dir: str | Path, method: str, *, blocks_path: str | Path | None,
         solar_fixture: str | Path | None, no_agent: bool, max_rounds: int, merge_flats: bool, client: Any | None,
         deadline: Deadline | None, lat_lng: tuple[float, float] | None, on_stage: Callable[[str], None],
         verify: bool, fallback_from: str | None, render: bool = True) -> PipelineResult:
    from . import agent as agent_mod
    from . import solar

    deadline = deadline or Deadline.after(10_000)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = slug(address)
    kw = {"merge_flats": merge_flats}
    started = time.monotonic()

    # 1. data stages
    if blocks_path:
        base = BlockSet.load(blocks_path)
    elif method == "solar_agent":
        base = _stage_footprint(address, lat_lng, deadline, on_stage)
    else:
        base = _stage_blocks(address, out, tag, lat_lng, deadline, on_stage)
    if not base.address.get("formatted"):
        base.address = {"line1": address, "city": "", "state": "", "zip": "", "formatted": address}
    fpinfo = base.extra.pop("_fp", None) or {"source": "lariac" if base.footprint_meta.get(
        "provider", "").startswith("lacounty") else "osm", "warnings": [], "codes": [], "other_buildings": 0}

    # 2. model stages
    deadline.check("model")
    on_stage("model")
    transcript: dict[str, Any] | None = None
    agent_fell_back: str | None = None  # one-line cause when the agent failed and the rules answered
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
                insights, live = solar.fetch_building_insights(ll.get("lat"), ll.get("lng"), _solar_key(),
                                                               timeout=deadline.timeout(30.0)), True
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
            res, cause = _try_agent(agent_mod, base, evidence, "solar", client, max_rounds, meta, deadline)
            if res is None:  # the agent failed: the rules answer on the same segment boxes
                agent_fell_back = cause
                classification = classify_blocks(model_blockset, **kw)
                classification.notes.append(f"The agent failed ({cause}); segment boxes classified by rules.")
            else:
                classification = Classification(blocks=res.blocks, notes=res.notes + agent_mod.agent_notes(res),
                                                warnings=res.warnings, gap_filled_pct=res.filled_pct)
                transcript = _transcript(res)
                source["agent"] = {"model": res.model, "api_calls": res.api_calls}
        roof_blocks = classification.blocks
    elif method == "lidar_agent" and not no_agent:
        res, cause = _try_agent(agent_mod, base, None, "lidar", client, max_rounds, None, deadline)
        if res is None:  # the agent failed: the rules answer, and the result says so
            agent_fell_back = cause
            classification = classify_blocks(base, **kw)
            classification.notes.append(f"The agent failed ({cause}); LiDAR blocks classified by rules.")
            roof_blocks = classification.blocks
            method, source["method"] = "lidar_skeleton", "lidar_skeleton"  # the caller sees what it really got
        else:
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
    net_exc: BaseException | None = None  # set when only the planes could be returned (planes_only.py)
    try:
        planes_only.need_roof_blocks(roof_blocks, base, fpinfo)
        model = build_model(model_blockset, roof_blocks, source, classification)
    except (ValueError, ShapelyError) as exc:
        try:
            if method not in AGENT_METHODS or no_agent or agent_fell_back:
                raise
            # the agent's blocks built a roof the model rejects (a sliver facet): the rules answer instead
            agent_fell_back = _cause(exc)
            classification = classify_blocks(model_blockset if method == "solar_agent" else base, **kw)
            roof_blocks = classification.blocks
            classification.notes.append(f"The agent's blocks did not build ({agent_fell_back}); classified by rules.")
            source.pop("agent", None)
            if method == "lidar_agent":
                method, source["method"] = "lidar_skeleton", "lidar_skeleton"
            planes_only.need_roof_blocks(roof_blocks, base, fpinfo)
            model = build_model(model_blockset, roof_blocks, source, classification)
        except (ValueError, ShapelyError) as final:
            net_exc = final
            model = planes_only.model_or_raise(final, base, source, fpinfo, _cause(final))

    if net_exc is None and method == "lidar_agent" and not no_agent and not agent_fell_back:
        better = agent_pick.rules_if_not_worse(base, model, fpinfo["codes"], **kw)
        if better is not None:  # the agent drew a roof that fits the planes worse than the rules' roof
            classification, roof_blocks, agent_fell_back = better
            classification.notes.append(f"The agent's roof was not used: {agent_fell_back}.")
            source.pop("agent", None)
            method, source["method"] = "lidar_skeleton", "lidar_skeleton"
            model = build_model(model_blockset, roof_blocks, source, classification)  # the transcript stays on disk

    from_planes, was_planes_only, old_metrics = False, False, {}  # the block model is poor but the measured planes tile the roof: draw those instead
    if method != "solar_agent":
        was_planes_only = net_exc is not None
        drawn = planes_model.replace_if_bad(base, model, source, was_planes_only, fpinfo["codes"])
        if drawn is not None:
            (model, old_metrics), net_exc, from_planes = drawn, None, True

    # 3. verifier, then outputs from the FINAL model
    deadline.check("verify")
    if from_planes:  # never read a planes model as verified
        verification, verifier_transcript = _no_verification(model, planes_model.NOT_VERIFIED), []
    elif net_exc is None:
        model, verification, verifier_transcript = _verify(model, verify, client, deadline, on_stage)
    else:  # a planes-only result has no edges to verify
        verification, verifier_transcript = _no_verification(model, planes_only.NOT_VERIFIED), []
    on_stage("render")
    extra_warnings: list[tuple[str, str]] = []
    if net_exc is not None:
        extra_warnings.append((planes_only.CODE, planes_only.WARNING))
        render = False  # the debug picture draws facets
    if from_planes:
        extra_warnings.append((planes_model.CODE, planes_model.WARNING))
        if was_planes_only:
            extra_warnings.append((planes_only.CODE, planes_only.WARNING))
    if agent_fell_back:
        text = (f"The roof agent's roof was not used ({agent_fell_back}); the rule-based measurement was used instead."
                if agent_fell_back.startswith("its roof")
                else f"The roof agent could not finish ({agent_fell_back}); the rule-based measurement was used instead.")
        extra_warnings.append((AGENT_FELL_BACK, text))
    paths = {"blocks": out / f"{tag}_blocks.json", "model": out / f"{tag}_model.json",
             "png": out / f"{tag}_model.png"}
    base.extra.pop("_geo", None)
    base.save(paths["blocks"])
    if not render:
        paths.pop("png")
    else:
        try:
            render_png(model, paths["png"])
            model["debug"]["png"] = paths["png"].name
        except ImportError:  # the `render` extra (matplotlib) is not installed: skip the picture, no warning
            log.warning("render skipped: matplotlib is not installed (install the render extra)")
            paths.pop("png", None)
        except Exception as exc:  # the debug picture never fails a finished measurement
            log.warning("render failed: %s", type(exc).__name__, exc_info=True)
            paths.pop("png", None)
            extra_warnings.append(("other", "The debug picture could not be rendered."))
    write_model(model, paths["model"])
    if verify:  # empty list when only the deterministic merge ran
        paths["verifier_transcript"] = out / "verifier_transcript.json"
        paths["verifier_transcript"].write_text(json.dumps(verifier_transcript, indent=1, default=str))
    if transcript is not None:
        paths["transcript"] = out / "agent_transcript.json"
        paths["transcript"].write_text(json.dumps(transcript, indent=1, default=str))

    density = ((model.get("source") or {}).get("lidar") or {}).get("density_per_m2")
    verification = cap_verification(verification, fpinfo["source"])  # final verdict before the warnings
    warnings, codes = collect_warnings(model, fpinfo, verification, density, fallback_from, method, extra_warnings)
    assessment = _assess(base, model, codes) if method != "solar_agent" else None
    if from_planes and assessment and assessment.get("quality"):
        assessment["quality"]["reasons"].insert(0, planes_model.REASON)  # first: a planes model is never "verified"
        assessment["quality"].update(old_metrics)  # what the replaced block model scored
    if net_exc is not None:
        assessment = planes_only.assessment_or_raise(assessment, net_exc)
        verification = {**verification, "original_totals": {k: v for k, v in planes_only.planes_only_totals(
            assessment["totals"]).items() if k in TOTALS_KEYS}}
    envelope = build_envelope(model, method_used=method, footprint_source=fpinfo["source"], verification=verification,
                              warnings=warnings, warning_codes=codes, density_pts_m2=density, assessment=assessment)
    if assessment:
        write_model(model, paths["model"])  # the file on disk carries the same optional keys as the envelope
    log.info("pipeline done method=%s footprint_source=%s verdict=%s ms=%d", method, fpinfo["source"],
             envelope["verification"]["verdict"], int((time.monotonic() - started) * 1000))
    return PipelineResult(model=model, blockset=base, paths=paths, agent_transcript=transcript, method_used=method,
                          footprint_source=fpinfo["source"], verification=envelope["verification"],
                          envelope=envelope, density_pts_m2=density,
                          transient=bool(fpinfo.get("transient")))


def _assess(base: BlockSet, model: dict[str, Any], codes: list[str]) -> dict[str, Any] | None:
    """Quality metrics and snapped planes from the LiDAR blocks.

    A failure never fails the measurement: it is logged and the envelope carries ``quality`` with the reason
    ``quality_failed`` (no planes, no plane totals), so a consumer can tell a failed check from "no LiDAR".
    """
    if not base.blocks:
        return None
    from .quality import assess, failed_assessment

    try:
        return assess(base, model, codes)
    except Exception:
        log.warning("quality assessment failed", exc_info=True)
        return failed_assessment(model, codes, len(base.blocks))


def _cause(exc: BaseException) -> str:
    """A one-line, bounded cause for the warning: the class and the first 120 characters of its text."""
    return f"{type(exc).__name__}: {' '.join(str(exc).split())[:120]}".rstrip(": ")


def _try_agent(agent_mod: Any, base: BlockSet, evidence: list[dict[str, Any]] | None, kind: str, client: Any | None,
               max_rounds: int, imagery: dict[str, Any] | None, deadline: Deadline) -> tuple[Any, str | None]:
    """``(result, None)``, or ``(None, cause)`` when the agent failed and the rules should answer.

    The agent is an upgrade, never a new way to fail: its own errors, a shapely error, a timeout of the agent
    stage and any other ``Exception`` from its path fall back (``BaseException`` does not). The agent runs on ``AGENT_BUDGET_SHARE`` of the time left; when the whole job is out of time
    the timeout is the answer and is raised. A missing API key and an invalid or revoked one (``agent.AgentAuthError``, a
    ``PipelineError``) are caller errors and are raised too.
    """
    budget = Deadline.after(deadline.remaining() * AGENT_BUDGET_SHARE)
    try:
        return _run_agent(agent_mod, base, evidence, kind, client, max_rounds, imagery, budget), None
    except PipelineError as exc:
        cause = exc.__cause__
        if isinstance(cause, agent_mod.AgentError):
            return None, _cause(cause)
        raise
    except (ShapelyError, DeadlineExceeded) as exc:
        if isinstance(exc, DeadlineExceeded) and (deadline.expired() or exc.stage != "agent"):
            raise
        return None, _cause(exc)
    except Exception as exc:  # the agent is never a new way to fail: any bug in its path falls back
        log.warning("agent stage failed unexpectedly (%s); using the rules", type(exc).__name__, exc_info=True)
        return None, _cause(exc)


def _run_agent(agent_mod: Any, base: BlockSet, evidence: list[dict[str, Any]] | None, kind: str,
               client: Any | None, max_rounds: int, imagery: dict[str, Any] | None,
               deadline: Deadline | None = None) -> Any:
    if client is None and not config.anthropic_key():
        raise PipelineError("The agent method needs an Anthropic API key (the anthropic_api_key argument or "
                            "ANTHROPIC_API_KEY).")
    try:
        return agent_mod.run_agent(base, evidence, kind=kind, client=client, max_rounds=max_rounds, imagery=imagery,
                                  deadline=deadline)
    except agent_mod.AgentError as exc:
        raise PipelineError(f"The agent failed: {exc}.") from exc


def _transcript(res: Any) -> dict[str, Any]:
    return {"model": res.model, "api_calls": res.api_calls, "usage": res.usage, "decisions": res.decisions,
            "filled_pct": res.filled_pct, "messages": res.transcript}
