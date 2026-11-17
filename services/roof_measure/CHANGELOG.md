# roof_measure changelog

## 0.4.0 (pipeline version; contract name unchanged, see ../../docs/contract-0.3.md)

<!-- Sections below are merged by the director from the three builders of the roof-houses round. -->

### Every building on the lot (bf-lot)
- New optional `measure(..., include_other_buildings=False)`. With `True` the other county outlines of the parcel
  (at least 120 sq ft, at most six) are measured with `lidar_skeleton` (no agent, no verifier) in the same child and
  deadline, and the envelope gains the optional top-level `other_buildings` (index, footprint, `offset_ft`, status,
  `error_code`, model, totals per building, largest first) and the totals `lot_buildings`, `lot_area_sqft`,
  `lot_squares`, `lot_outline_perimeter_ft`. The default changes nothing. A failing building is recorded as `failed`;
  a crashed child is retried once without the extra buildings. New module `lot.py`; `run_pipeline` and the child take
  `include_other_buildings`. `Footprint.other_info` (id and area per other outline) is new and additive.
- `PIPELINE_VERSION` 0.3.1 to 0.4.0 (keys the result cache: cached 0.3.1 results are recomputed). The four 0.2 example
  fixtures carry the new version string (only that line changed); the planes-only example
  `fixtures/roof_planes_only/roof_measurement_0.3_planes_only.json` was regenerated and its four planes are redrawn
  by the straightening.

### Parcel street match (bf-lot)
- The county parcel's street now compares after normalisation (`street_names.normalize_street`): "Ave B" and
  "AVENUE B" (also ST/STREET, DR/DRIVE, directionals, "1st"/"first", unit designators) are the same street, so a
  lead that differs from the situs address only by abbreviation is an `exact` match with no `parcel_street_match`
  warning. Behaviour change for inputs that worked: such an address used to get the `street` match and the warning
  (and its planes were then not clipped to the footprint); it now gets the exact-match behaviour. A different house
  number, street name or street type is still not exact (the old check also accepted "Oak Ave" for "OAK DR"; that
  false exact match is gone).

### Planes partitioned by their plane equations (bf-envelope)
- New internal step `planes_envelope` after straightening: each roof section's planes are redrawn as the lower
  envelope of their plane equations (ridges, hips and valleys where the planes' heights agree; straight axis steps
  between sections; facings within 10 deg of the building axis squared; parallel planes of one face share an
  equation). Used only when its never-worse gate passes, else the straightened planes stay. Behaviour change for
  inputs that work today: `model.planes` polygons and areas change on roofs where the gate passes (the totals stay
  within the gate: plan area = outline within 1%, surface within 5%); planes carry the optional `straighten_method`
  ("envelope" | "arrangement") and `section`; `plane_eq` is the squared equation; snap borders use the kinds ridge,
  hip, valley, step, seam (seam = one face cut in two, not a roof line) instead of intersection/step.
- Developer tool `tools/envelope_png.py` (before/after picture of a blocks file).

### The agent method, never a downgrade (bf-agent)
- Never a new way to fail: every sloped block is checked after tiling with the model builder's own geometry call; a
  refusal goes back to the agent as a readable `finalize` error; on its last round a gable that cannot be extended
  becomes a hip (noted in the model); anything the model still rejects falls back to the rule result, then to the
  planes-only result. A plain `ValueError` out of the model build is handled like `ModelError`.
- Draws multi-section roofs: new tools `levels`, `split_between`, `clean_outline`, `check_draft`; the prompt works by
  height first and ridge second and iterates on its own score; gable ends are remapped after tiling; the blocks are made
  a partition (the higher block wins an overlap, outlines opened and closed, facets under 12 sq ft removed, slivers to
  the neighbour with the longest edge); gables on outlines the skeleton cannot extend are drawn from their ridge line
  (`RoofBlock.ridge_gable`, `skeleton.hip_roof_edges(..., ridge_fallback=True)`; off by default); prompt caching on the
  evidence cuts input tokens about 5x. `usage` may carry `cache_creation_input_tokens` / `cache_read_input_tokens`.
- `lidar_agent` returns the rule result when the agent's roof matches the measured planes worse or equally (lower plane
  mismatch wins, ties to the rules): `method_used` `lidar_skeleton`, warning `agent_failed_fell_back`.
- Developer tools `tools/eval_agent.py`, `tools/eval_png.py`.

### A model built from the measured planes (bf-agent)
- When the block (or agent) model is poor (`plane_mismatch_pct` >= 15, `model_uncovered_pct` >= 10, or planes-only) and
  the partition planes (`straighten_method` "envelope" or "arrangement") tile the outline (>= 95% covered, overlap <= 1%,
  3 to 12 vertices a facet, area within 3%, and for a replacement: no unspecified edge, transitions under 20% of the
  interior edges, a ridge or hip, own typing within 15% of the envelope's kinds), the model is built directly from the
  planes: one facet and one `shed` block per plane, every shared edge typed once from the envelope's border kind
  (ridge, hip, valley, step; a seam draws nothing), outer edges from the plane's slope (eave low side, rake along the
  slope, ridge on the high side of a single plane, parapet for a flat plane). `model.source.from_planes` true, warning
  `model_from_planes`, `model.quality.reasons` starting with `from_planes`, `model.quality.block_model_mismatch_pct` and
  `block_model_uncovered_pct` (what the replaced model scored; null when it was planes-only), verification
  `unverified`, `method_used` unchanged. A planes-only result is replaced by any planes that pass the first gate and
  keeps its `model_failed` warning. A tapering height step (an envelope `hip` whose median step is 1.5 ft or more) is
  drawn as a `transition` and adds to no cap or flashing total. Roofs that are good by the metrics keep their model
  byte for byte (their `model.planes`, plane totals and quality metrics still move with the partition above).
- New warning code `model_from_planes` (in `envelope.WARNING_CODES`).

### Complex roofs and the geometry review (bf-complex)
- Step lines between sections: a border the old fit drew diagonally is now a square wall: the level line (eave or top
  edge) of a square pitched plane it bounds, at the measured border, with a leg to the outline where the measured
  border meets it; a diagonal stays only where the clusters run side by side diagonally for 8 ft or more (a real
  angled wall); a step 0.5 ft or less beside a parallel outline wall it starts from is that wall; a one-plane section
  under 80 sq ft next to a diagonal border is boxed by its cluster. A border between multi-plane sections that one
  path misses by over 4 ft gets one step line per plane pair (a flat roof ringed by slopes). Axis-aligned steps are
  drawn exactly as before.
- A roof line ending in a T on another plane's straight edge now puts its end vertex on that edge too, so the border
  is found (before, a flat roof could have no border at all with a section whose lines ended on it). Output change
  for roofs that worked: one collinear vertex may be added to a plane's ring at such a junction (same polygon).
- Retry ladder inside the partition, all against the same never-worse gate: square steps; when that fails, a section
  of more than 8 planes partitioned part by part at its valleys (`planes_envelope_split`); then the round-2 steps.
  A roof that passed before is never re-drawn by a retry.
- Border kinds: `seam` only for planes facing within 10 degrees (was 45: a wing bent 20 degrees lost its hip and
  valley); two planes that both slope nearly along a line are typed by the small slope across it; a pitch break in
  one facing is `transition` (was `step`); a line is level (`ridge`, not `hip`) when its ends differ by at most 0.25 ft
  or 5% of its plan length (a level ridge turned a few degrees onto a diagonal stays a ridge).
- A plane that lies mostly outside the largest part of a multi-part region (street match: a detached carport) makes
  the partition refuse (the straightened planes stay) instead of vanishing.
- `filled_pct` of a partitioned plane is recomputed for its new polygon (the share LiDAR did not see); the planes-only
  example fixture was regenerated (only its four `filled_pct` values changed: 6.8/9.8/7.3/9.7 to 13.6/10.7/13.6/10.7).
- The planes model: a plane whose snapped ring pinches into two parts uses its largest part (an AttributeError used to
  fail the measurement); `replace_if_bad` never raises (any error keeps the block model); it no longer runs a second
  partition, so the facets always come from the planes published in `model.planes`; it keeps the replaced model's
  `source.lidar.fitted_area_sqft` and coverage notes, and its confidence is never above the replaced model's: at most
  "medium", "low" when the replaced result was planes-only (output change: such roofs said "medium").
- Other buildings: a building whose envelope has a non-finite number, or totals the lot sums cannot use, is recorded
  as `failed` (`measurement_failed`); the lot totals are written only when all are finite; attaching the lot never
  raises (on failure the main result has no `lot_*` keys and an `other` warning).
- Known limits: `eave_height_ft` of a planes-model block is the plane's mean height above its local ground; a plane's
  `pitch_rise` and `surface_area_sqft` come from its own fit while `plane_eq` may be the one-face mean; the partition
  calls a plane flat under 0.36/12 and the planes model under 0.5/12.

### Planes (bf-planes)
- `model.planes[]` entries carry the optional keys `straightened`, `raw_plan_area_sqft`, `plane_eq` (z = a*x + b*y + c,
  feet above the roof's one height datum), and, when the envelope partition was used, `straighten_method` and `section`.
  `SnapResult.borders` lists the borders between planes (`a`, `b`, `segment`, `length_ft`, `kind`, `step_ft`, `high`).

## 0.3.1 (pipeline version; contract name unchanged, see ../../docs/contract-0.3.md)

### Behaviour change for every caller of `lidar_skeleton`, `auto` and `lidar_agent` (additive for models that worked)
- **Inputs that used to raise `MeasureError` `measurement_failed` now succeed with a planes-only result** when LiDAR
  planes survive snapping: a block model that fails `model.validate` (most often "facet fN has a spike (x deg)"), or a
  classification with no roof block although planes exist. The envelope has `model.source.planes_only` true, empty
  `facets`/`edges`/`blocks`, `model.planes`, `model.quality` with `model_failed` as the first reason, every `totals`
  key (area, squares and pitch from the planes; the outline perimeter for `eave_ft` and the two drip-edge totals; all
  other edge totals 0.0 and NOT measured), the warning code `model_failed` and an unverified verification. `lidar_agent`
  gets the same net after its fall back to the rules. With no plane at all (no LiDAR, every plane outside the footprint,
  `solar_agent`) the error is raised as before. Callers that read "an envelope came back" as "a roof diagram exists"
  must check `model.source.planes_only` or the code.
- New warning code `model_failed` (in `envelope.WARNING_CODES`, contract-0.2 table, contract-0.3).
- Sliver repair (`model_slivers.py`, called by `model_cleanup.clean_facets`): a facet that fails validation with a spike
  and is under 25 sq ft and 2% of its block is merged into the same-block neighbour that removes the spike (longest
  shared border first). Measured on three real roofs that used to fail (one facet of 1 to 11 sq ft per spike, 0.1% to
  0.5% of the block); a model that passed before is never touched (pinned on every committed blocks fixture and checked
  on four real roofs: identical envelopes). A merged facet appears as a model warning ("facet fN: sliver merged into
  facet fM", code `other`).
- `PIPELINE_VERSION` 0.3.0 to 0.3.1 (appears in `/healthz`, `pipeline_version`, keys the result cache: cached 0.3.0
  results, including failures that are now planes-only results, are recomputed). The four 0.2 example fixtures were
  regenerated (only that line changed). New example `fixtures/roof_planes_only/roof_measurement_0.3_planes_only.json`.
- Known limit: the three real failures now build, but from jagged block outlines (up to 226 vertices) the skeleton
  yields 65 to 227 small facets; they score "rough" (see `model.quality`). The simple model is not better for them than
  the planes; the planes-only result is the honest answer when the model fails.

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
