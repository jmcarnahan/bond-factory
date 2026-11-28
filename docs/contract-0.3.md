# roof_measure envelope 0.3 (additive to 0.2)

> **Superseded by [contract-0.7.md](contract-0.7.md).** The block path, `planes_only` results, the agent fallback, the four plane totals made by plane snapping and the old totals keys described here were removed in 0.6.0. Kept as the record of the shape before.

> **Removed in 0.6.** The block path (and with it the `planes_only` result and the block-path quality object, `model.planes`
> snapping and the four plane totals it made), the agent methods, the verifier, Solar and the job service. See the note at the
> top of contract-0.2.md. The plane engine's quality, planes and totals (contract-0.4.md) remain.

`PIPELINE_VERSION` is `0.4.0` (0.3.0 added the keys below; 0.3.1 adds the planes-only result and a sliver repair, see the end of this file; 0.4.0 adds the optional `other_buildings` key, see "Other buildings on the lot"); the contract name stays `bond.roof_model/0.2` and every 0.2 key keeps its meaning and its
value. 0.3 only ADDS optional keys and three warning codes (`parcel_street_match`, `agent_failed_fell_back`, `model_failed`; and the street-match note moves from `other` to the first). A parser that ignores unknown keys (the Dart `RoofMeasurement`
does) needs no change. `method_used` never gains a new value: a retry or a fallback is a reason code, not a method.
`pipeline_version` keys the result cache, so 0.2.0 results are not reused after the upgrade.
The agent methods behave differently (they no longer raise on an agent failure): see "Agent methods" below and the CHANGELOG.

## What is added

Present whenever the pipeline had LiDAR blocks: `lidar_skeleton`, `lidar_agent` (a successful agent run too; the
metrics then judge the agent's model, and after a fallback the rule model), and `auto` when it stayed on LiDAR.
Absent, never null, for `solar_agent` and for a result with no blocks. **Absent never means "checked and good"**; and
if the check itself failed (logged on the service) `model.quality` is still there with the single reason
`quality_failed` and no numbers, so a consumer can tell a failed check from "no LiDAR".

`planes` and `quality` are internal library modules, not part of the package API; consumers read the envelope.

### `model.planes` (list)

The LiDAR planes, snapped: made disjoint (an overlap goes to the larger plane), gap-free (every uncovered part of the
outline goes to a neighbouring plane), tidied (spikes and zero-width necks removed, vertices closer than 0.5 ft merged
the same way on every plane so shared borders stay shared, no interior angle under 10 degrees) and, unless the parcel
was only a street match, clipped to the footprint. Pieces under 4 sq ft are dropped. Two snapped planes may still overlap by up to 0.5 sq ft and leave micro-gaps under 0.1 sq ft at their borders (the
snapping is clean to about 0.25 ft, not exact); the union equals the footprint within 1%. `[]` when LiDAR ran but no
plane survived (for example every plane lies outside the footprint). One object per plane:

| Key | Type | Meaning |
|---|---|---|
| `id` | string | the LiDAR block id (`k0`, ...) |
| `polygon` | [[x, y], ...] | exterior ring in feet, model frame, counter-clockwise, no repeated last point, 0.01 ft |
| `holes` | [[[x, y], ...], ...] | OPTIONAL, only when another plane lies inside this one: its rings (clockwise) |
| `pitch_rise` | number | rise over 12, 0.01; 0 for a flat plane |
| `aspect_deg` | number or null | compass downslope bearing; null for flat |
| `plan_area_sqft` | number | area of the polygon minus holes, 0.1 |
| `surface_area_sqft` | number | plan area divided by cos(atan(pitch_rise / 12)), 0.1 |
| `height_ft` | number | height above ground, 0.01 |
| `rms_ft` | number | plane-fit residual from LiDAR, 0.001 |
| `filled_pct` | number | share of this plane's final area that came from gap filling, 0.1 |
| `straightened` | bool | OPTIONAL (0.4.0): the plane's borders were redrawn as straight roof lines |
| `straighten_method` | string | OPTIONAL (0.4.0): how (`envelope`, `arrangement`, `lines`); absent when not straightened |
| `raw_plan_area_sqft` | number | OPTIONAL (0.4.0): the plan area of the LiDAR cluster before straightening, 0.1 |
| `plane_eq` | [a, b, c] | OPTIONAL (0.4.0): height in feet above the common ground datum = a*x + b*y + c, model frame |
| `section` | integer | OPTIONAL (0.4.0): planes with the same number meet without a height step |

Since 0.4.0 the plane polygons and areas of a roof whose planes could be straightened differ from 0.3.1 for every
caller (same keys, straighter borders); the model may also be drawn from these planes (see `model.source.from_planes`).

### `model.quality` (object): metrics only, no label

| Key | Meaning |
|---|---|
| `plane_mismatch_pct` | area-weighted share of the snapped planes whose best-overlap model facet differs by more than 30 degrees of aspect or more than 1.5/12 of pitch. Flat meets flat only: a plane or facet with no aspect, kind `flat` or a pitch under 0.5/12 is flat, and a flat one never meets a sloped one. Null when there are no planes or the check failed. 0.1 |
| `outline_covered_pct` | share of the FOOTPRINT the raw cleaned planes covered before gap filling, measured on the footprint also when the planes are not clipped (street match); 0.0 when no plane touches it; null only when the check failed. 0.1 |
| `model_uncovered_pct` | share of the snapped planes' total plan area that lies OUTSIDE the union of the model's facets (plan view): the extent the model loses, which the mismatch cannot see. 0 when the model covers every plane, 100 when the model has no facet; null with no planes or when the check failed. 0.1 |
| `level_spread_ft` | highest minus lowest plane `height_ft` among the planes that cover at least 5% of the planes' area; a two-level roof shows several feet, a single-level one about 0. Null as above. 0.1 |
| `planes_lidar` | number of snapped planes (= `model.planes` length); when the check failed, the number of LiDAR planes found |
| `facets_model` | number of facets in `model.facets` |
| `reasons` | codes, in this order when present: `model_failed` (planes-only result: first, see the end of this file), `multi_plane_simplified` (planes_lidar >= facets_model + 3 and mismatch >= 30), `low_outline_coverage` (covered < 70), `model_misses_roof_area` (`model_uncovered_pct` >= 10), `sparse_lidar` (the `low_point_density` warning), `parcel_street_match`, `other_buildings_on_parcel`, `agent_failed_fell_back` (a `lidar_agent` run fell back to the rules; the retry after a crashed process adds it too), `bad_lidar_block` (a LiDAR block with a NaN or infinite number was left out), `quality_failed` (first and alone but for the copied codes when the check failed) |

Read the metrics together, never `plane_mismatch_pct` alone: a single small LiDAR plane can be snapped over the whole outline and score a mismatch of 0.0. `outline_covered_pct` (and the reason `low_outline_coverage`) says how much of the outline the raw planes really covered, and `model_uncovered_pct` how much of the planes' area the model does not draw.

The consumer decides what is good or rough; the library applies no threshold beyond the reason codes. Point residuals
are not part of the envelope (points are dropped before the model is built).

### `totals` (four more keys, same presence rule; absent when no plane survived or the check failed)

| Key | Meaning |
|---|---|
| `planes_surface_area_sqft` | sum of the planes' surface areas, 0.1 (compare with `area_sqft`) |
| `planes_pitch_weighted` | plan-area-weighted pitch of the planes (rise over 12; flat counts 0), 0.1 |
| `outline_perimeter_ft` | perimeter of the OUTER ring of the union of the planes, 0.1 (courtyard rings and holes are not counted; several separate parts add up) |
| `plane_count` | number of planes |

### Warning codes

`agent_failed_fell_back` (a `lidar_agent`/`solar_agent` run fell back to the rules; see the table in contract-0.2.md 2.3) and `parcel_street_match`, below.

### Warning code `parcel_street_match`

The note "no exact parcel match; used parcel ... (street match)." (also "(nearest match)") now has code
`parcel_street_match` instead of `other`; the sentence is unchanged. It is in the closed list of 2.3. When it is present
the planes are NOT clipped to the footprint (the footprint may belong to a neighbour): they cover the raw planes with
their holes closed; `outline_covered_pct` is still measured against the footprint, so `low_outline_coverage` can fire.

## Evaluating a roof offline

`make -C services/roof_measure eval BLOCKS=<file-or-dir>` runs the rule method on saved block files (no network, no
keys) and prints one row per file: planes, facets, mismatch, coverage, model area, planes surface area, pitch (model /
planes) and reasons. `ARGS="--json out.json --svg dir --envelopes dir"` also writes the metrics, a side-by-side SVG
(model facets left, snapped planes right) and the full envelopes.

## Agent methods (`lidar_agent`, `solar_agent`)

A failure of the agent (API error, truncated or refused reply, no final answer, a geometry error, a timeout of the
agent stage, blocks the model builder rejects) no longer raises: the rule result is returned with the warning code
`agent_failed_fell_back` (see 2.3 of contract-0.2). `method_used` is then `lidar_skeleton` for `lidar_agent`
(`solar_agent` keeps its name: Solar segments have no LiDAR). **A caller that treats "I got an envelope" as "the agent
ran" must check `method_used` or the code.** A `lidar_agent` child killed by a signal is retried once as
`lidar_skeleton`; a `solar_agent` crash still fails the measurement. `solar_agent` plus `agent_failed_fell_back` means the Solar segments were classified by the rules (`method_used` keeps
the name; there is no new method value). A missing, invalid or revoked Anthropic key is NOT
a fallback: it raises (`measurement_failed`, not retryable).

## Planes-only result (`model_failed`, pipeline 0.3.1)

Before 0.3.1 a roof whose block model failed validation (for example `measurement_failed: facet f45 has a spike (9.6
deg)`) or came out of the classifier with no roof block was an ERROR although the LiDAR planes had been found. Now,
for `lidar_skeleton`, `auto` and `lidar_agent` (after its fall back to the rules), when LiDAR planes survive snapping
the call SUCCEEDS with a planes-only envelope. **These inputs used to raise `MeasureError` `measurement_failed`**; a
caller that treats "an envelope came back" as "a roof diagram exists" must check `model.source.planes_only` or the
warning code. With no plane at all (no LiDAR, every plane outside the footprint, `solar_agent`) the error is raised
as before.

| Where | Value |
|---|---|
| `model.source.planes_only` | `true` (the key is absent otherwise, never `false`) |
| `model.facets`, `model.edges`, `model.blocks`, `model.holes` | `[]`; `model` still passes `validate` (schema `bond.roof_model/0.1`), its `totals` are zeros |
| `model.confidence` | `overall` `low`, notes: the sentence "The simple roof diagram could not be built; this result is the measured roof planes only." and the cause (the validation message) |
| `model.planes` | as always (snapped planes); at least one |
| `model.quality` | `plane_mismatch_pct` null; `model_uncovered_pct` 100.0; `facets_model` 0; `reasons` start with `model_failed`; `multi_plane_simplified` and `model_misses_roof_area` are not given (the first reason says it), the others are kept (`low_outline_coverage`, `sparse_lidar`, ...) |
| `totals` | every 0.2 key is present: `area_sqft` = `planes_surface_area_sqft`; `squares` = area / 100; `predominant_pitch` = the half-step bucket of `planes_pitch_weighted`; `facets` 0; `eave_ft`, `drip_edge_eave_ft`, `drip_edge_eave_rake_ft` = `outline_perimeter_ft`; `rake_ft`, `ridge_ft`, `hip_ft`, `valley_ft`, `step_flashing_ft`, `ridge_cap_ridge_ft`, `ridge_cap_ridge_hip_ft` = 0.0; plus the four plane totals. **The edge totals are NOT measured**: only the outline perimeter is known, it stands in for the eaves, and the other edge types are 0.0 because nobody measured them. Show the area, the pitch and the perimeter; do not offer ridge, hip or valley lengths |
| `warning_codes` / `warnings` | `model_failed`: "A simple roof diagram could not be built; the measured roof planes are returned instead." (with `agent_failed_fell_back` when that happened first) |
| `verification` | verdict `unverified`, `rounds` 0, `model` null, `adjustments` `[]`, a note that there were no edges to verify; `original_totals` are the totals above. The verifier does not run, whatever `verify` says |
| `confidence` | 0.5 or lower (a low-confidence model, capped as always) |
| `method_used` | the method that ran (`lidar_skeleton`, or `lidar_skeleton` after an agent fell back) |

A consumer that draws the roof diagram must not draw it from a planes-only model (`facets` is empty): draw
`model.planes` instead. The Dart `RoofModel.fromJson`, `LengthDiagram`, `AreaDiagram`, `SummaryBlock` and
`RoofReport.pages` accept such a model without throwing (they draw a page with the legends and no roof;
`packages/bond_roof/test/planes_only_test.dart`; the test and the example file were removed with the 0.6 round, superseded).

### Sliver repair (pipeline 0.3.1)

`model.validate` rejects a facet vertex sharper than 10 degrees. When the pipeline's own straight skeleton produces a
facet that is a spike and tiny (area under 25 sq ft and under 2% of its block), the facet is merged into the
same-block neighbour it shares the longest border with, provided the merged facet has no spike left; the block still
tiles exactly and the area does not change. The edge between the two facets disappears and the sliver's other edges
belong to the neighbour. A warning (code `other`) names each merge. A model that passed validation before is never
changed (the repair runs only for a facet that would fail).

## Other buildings on the lot (pipeline 0.4.0)

`measure(..., include_other_buildings=False)`: a new optional keyword. With the default it adds nothing (no
`other_buildings`, no `lot_*` totals; other 0.4.0 changes still apply: on roofs whose planes are straightened and
partitioned, `model.planes`, the plane totals and the quality metrics change, and a poor block model can be replaced
by one built from the planes; no key is renamed or removed). When `True`, after the main building has
been measured the library measures every other county outline of the parcel that is at least 120 sq ft (the county
link already keeps only outlines with at least half of their area inside the parcel; at most the six largest) with
the rule method (`lidar_skeleton`: no agent, no verifier), inside the same deadline and the same child process, each
building getting at most a fair share of the time left (`remaining / buildings_left`; under 8 s the building and the
ones after it are skipped). Only the LA County source has several outlines today; for any other footprint source, a
blocks fixture or a lot with no second outline the call is a no-op. The existing warning
`other_buildings_on_parcel` is unchanged.

The main envelope then gains ONE optional top-level key, absent otherwise (never null):

```
"other_buildings": [        // largest first
  {"index": 1,              // 1.., the order of this list
   "footprint": {"provider": "...", "id": "...", "area_sqft": 424.0},
   "offset_ft": [dx, dy],   // east, north, plan feet: this model's origin as seen from the main model's origin
   "status": "ok" | "planes_only" | "failed",
   "error_code": null | "<job code of errors.JOB_CODES, e.g. timeout, measurement_failed>",
   "model": { ... },        // the same object as envelope.model (quality and planes included); null when failed
   "totals": { ... } }      // the same keys as envelope.totals; null when failed
]
```

`offset_ft` is how a client puts both models on one sheet: draw the second model's points at `point + offset_ft` in the
main model's feet frame. Both models use the same north (the UTM grid of the main model's zone) and feet; each has its
own origin (the south-west corner of its own bounding box), which is why the offset exists (`dx = (x0_other -
x0_main) / 0.3048`, same for `y`, from the two frames' metric origins in the same CRS). `status` `planes_only` is the
same condition as the main model's `source.planes_only` (empty facets, `model.planes` only). A building that fails
or runs out of time is listed with `status` `failed`, a job code in `error_code`, and no model, totals or offset; the
main result is unaffected, and the main `warnings` gain one `other` note naming the codes. A native crash of the child
process while the extra buildings were measured is retried once without them (same note).

Four NEW keys in the main `totals` (present only with the key above); every existing totals key keeps meaning "the main
building":

| Key | Meaning |
|---|---|
| `lot_buildings` | number of buildings in the lot totals: the main one plus the `ok` and `planes_only` others |
| `lot_area_sqft` | sum of `area_sqft` over those buildings |
| `lot_squares` | sum of `squares` over those buildings |
| `lot_outline_perimeter_ft` | sum of `outline_perimeter_ft` over those buildings (`eave_ft` when a building has no such key) |



## Model from the measured planes (`model_from_planes`, pipeline 0.4.0)

When the block (or agent) model is poor (`model.quality.plane_mismatch_pct` >= 15, `model_uncovered_pct` >= 10, or the
result would be planes-only) and the LiDAR planes were partitioned by the envelope (`planes[].straighten_method` is
`envelope` or `arrangement`) and tile the outline, `model` is built from the planes instead. Shape: the ordinary
`bond.roof_model/0.1`, one facet per plane and one `shed` block per plane (`flat` for a flat plane,
`ridge_azimuth_deg` null), edges typed from the plane borders. Optional additions:

| Where | Key | Meaning |
|---|---|---|
| `model.source` | `from_planes` | true on such a model; absent otherwise |
| `model.quality` | `block_model_mismatch_pct`, `block_model_uncovered_pct` | what the replaced block/agent model scored (0.1); null when it was a planes-only result; present only with `from_planes` |
| `model.quality.reasons` | `from_planes` | FIRST in the list when present |
| warnings | `model_from_planes` | "The diagram was built from the measured roof planes." A replaced planes-only result keeps `model_failed` as well |

`method_used` is the method that ran. `verification.verdict` is `unverified` (a from-planes model is never verified). A
tapering height step (an envelope `hip` whose median step is 1.5 ft or more) is an edge of type `transition`: it adds to
no flashing or cap total. Roofs that are good by the metrics are unchanged byte for byte.
