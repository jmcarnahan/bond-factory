# roof_measure changelog

## 0.3.0 (pipeline version; contract name unchanged, see ../../docs/contract-0.3.md)

### Output changes for every caller (additive; every existing key and value is unchanged)
- New optional `model.planes`, `model.quality` and the totals `planes_surface_area_sqft`, `planes_pitch_weighted`,
  `outline_perimeter_ft`, `plane_count`. Present whenever LiDAR blocks were used (any method but `solar_agent`);
  absent otherwise. If the quality check itself fails, `model.quality` has the single reason `quality_failed` and no
  numbers (no planes, no plane totals). `model.quality` also carries `model_uncovered_pct` (share of the planes' plan area outside the model's facets), `level_spread_ft` (highest minus lowest plane height among planes with >= 5% of the area) and the reason `model_misses_roof_area` (uncovered >= 10). Reasons also include `bad_lidar_block` (a NaN/infinite block was left out). Absent never means "checked and good".
- New warning code `parcel_street_match`: the "no exact parcel match; used parcel ... (street match)" note had code
  `other`; the sentence is unchanged. Consumers keying on `other` for it must switch.
- New warning code `agent_failed_fell_back` (see below). Both codes are in `envelope.WARNING_CODES`.
- `PIPELINE_VERSION` 0.2.0 to 0.3.0: appears in `/healthz` and `pipeline_version`, and keys the result cache, so every
  cached 0.2.0 result is recomputed. The four 0.2 example fixtures were regenerated (only that line changed).
- A street-matched parcel's planes are not clipped to the footprint (the footprint may be the neighbour's).

### Behaviour changes for callers of `lidar_agent` and `solar_agent`
- An agent failure (API error, truncated or refused reply, no final answer, a geometry error, a timeout of the agent
  stage, blocks the model builder rejects) used to raise; it now returns the rule-based result with warning code
  `agent_failed_fell_back`. `method_used` is `lidar_skeleton` for `lidar_agent` (`solar_agent` keeps its name). Check
  `method_used` or the code if "an envelope came back" used to mean "the agent ran". `lidar_skeleton` and `auto` are
  untouched.
- A `lidar_agent` child process killed by a signal (a CGAL segfault) is retried once as `lidar_skeleton` when at least
  20 s of the deadline remain; the result carries the same code. A `solar_agent` crash still fails the job.
- A missing, invalid or revoked Anthropic key is NOT a fallback: it raises `measurement_failed` (not retryable).
- Agent requests now send `thinking={"type": "between_tools"}` and `max_tokens` 12000 (was 6000, no thinking field):
  more output tokens and cost per round. `stop_reason == "max_tokens"` and a refusal are now an agent error (so a
  fallback).
- NOT VERIFIED LIVE: the agent request shape was copied from the verifier (`verify_llm.py`) and has not been exercised
  against the live Anthropic API in this change (no key, no network in the tests). Run one real `lidar_agent` before
  relying on it.
- `skeleton.hip_roof_edges` (and so the agent's tools and any direct caller) now raises `ValueError` for rings CGAL
  cannot take (self-intersecting, repeated vertex, edges under 5e-6 ft, clockwise, not simple; see `skeleton_guard.py`; the thresholds are what 0.2.0 handled, 0 of 480 old-versus-new comparisons differ) instead
  of crashing or hanging the process. The rule path catches it and falls back to the block's rectangle with a note.
- A child killed by a signal is reported as `ChildCrashed` (a `MeasureError` subclass, code `measurement_failed`) with a
  message naming the signal and the end of the child's stderr, replacing the old generic text; anything matching the
  old message text must change.

### Tools
- `tools/eval_blocks.py` and `make eval BLOCKS=<file-or-dir>`: offline table / JSON / SVG for judging a roof. `make lint`
  now covers `tools/` too. New internal modules `planes*.py`, `quality.py` (not exported from the package).

### Known limitation (rule method)
- Connected planes of the same directions on different levels are fitted as ONE block at the area-weighted pitch (same
  root cause as the two-level L roof): a plain gable house with a lower attached gable scores mismatch about 14%
  (2 facets for 4 planes, the attached bay missing); `tests/test_residential_fixtures.py` pins it. Plain gable and hip
  houses score 0%. `model.quality.mismatch` sees pitch and direction only; `model_uncovered_pct` (18.8 on that house) and the reason `model_misses_roof_area` see the lost extent.
