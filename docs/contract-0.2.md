# Roof measurement service contract 0.2

`bond.roof_model/0.2` is the result envelope of the `roof_measure` service. The service is private: it is deployed
as a Docker image (GPL straight skeleton through compas_cgal) and apps talk to it only over HTTP. This document is
what an app copies: the API, the envelope, the error codes, the environment variables and one example. The model
inside the envelope is `bond.roof_model/0.1`, specified in [contracts/roof_model.md](contracts/roof_model.md).

## 1. API

Base URL is wherever the service is deployed. JSON in, JSON out. Every route except `GET /healthz` needs
`Authorization: Bearer <ROOF_MEASURE_TOKEN>`. The token lives in the calling app's backend only; a Flutter client
never holds it.

- `GET /healthz` returns 200 `{"status": "ok", "pipeline_version": "0.2.0"}`. It touches neither disk nor network and
  needs no token.
- `POST /v1/measurements` body
  `{"address": str (at most 200 characters), "lat"?: float, "lng"?: float,
  "method"?: "auto" | "lidar_skeleton" | "lidar_agent" | "solar_agent" (default "auto"),
  "verify"?: bool (default true), "force"?: bool (default false)}`
  returns `202 {"id": str, "status": "queued"}`.
  - If a finished result exists for the same request and `force` is false, the answer is `202 {"id", "status": "done"}`
    for a new id whose GET returns the cached result, so a poll loop needs no special case.
  - `lat` and `lng` are given together or not at all (lat in [-90, 90], lng in [-180, 180]). With coordinates the
    service skips geocoding and `address` is only a label.
  - Anything invalid is `422 invalid_request`. A full queue is `429 queue_full` with `Retry-After: 30`.
- `GET /v1/measurements/{id}` returns
  `{"id", "status": "queued" | "running" | "done" | "failed", "stage"?: str, "error"?: {code, message, retryable},
  "result"?: <envelope>}`. `stage` (geocode, footprint, lidar, blocks, model, verify, render) appears while
  `running` and is for display only. Poll every 2 seconds. An unknown id is `404 unknown_job`: the service keeps
  jobs on disk, but a client that gets a 404 should simply submit again.

### 1.1 Error object

Every non-2xx answer and every failed job carries the same object:

```json
{"error": {"code": "queue_full", "message": "The service is busy; retry shortly.", "retryable": true}}
```

`message` is for logs and support, never for end users (for job failures it carries the pipeline's own one-line text): map `code` to your own strings. `retryable` says whether
submitting the same request again can succeed.

| Code | Where | HTTP | Retryable | Meaning |
|---|---|---|---|---|
| `invalid_request` | request | 422 | no | body failed validation |
| `unauthorized` | request | 401 | no | token missing or wrong (also sends `WWW-Authenticate: Bearer`) |
| `unknown_job` | request | 404 | no | no such job id |
| `queue_full` | request | 429 | yes | the bounded queue is full |
| `address_not_found` | job | - | no | the geocoder found no match |
| `no_footprint` | job | - | no | no building outline from any source |
| `ambiguous_building` | job | - | no | two buildings of similar size near the point; send roof coordinates |
| `no_lidar_coverage` | job | - | no | no USGS 3DEP LiDAR covers the building |
| `lidar_too_sparse` | job | - | no | LiDAR exists but is too thin on the roof |
| `measurement_failed` | job | - | no | the pipeline could not produce a valid model |
| `upstream_unavailable` | job | - | yes | a data source could not be reached |
| `timeout` | job | - | yes | the job ran past `ROOF_MEASURE_JOB_TIMEOUT_S` |
| `interrupted` | job | - | yes | the service restarted while the job was running |

A job failure is `200` on the GET with `"status": "failed"`.

### 1.2 Caching

The result cache key is the SHA-256 of the geocoder's matched address (upper case, unit tokens removed, ZIP5) or of
`ll:<lat>,<lng>` rounded to 5 decimals, plus the requested method, `verify`, the pipeline version, and whether the
Google Solar and Anthropic keys are configured. Two spellings of one address therefore share a result. `force: true`
skips the result cache and the fetch cache for that job.

Identical requests that arrive while one is running are coalesced: each gets its own id and all resolve with the
same result. A cached envelope reached by `lat`/`lng` carries the address label of the first request that produced it.
`force: true` re-downloads the fetch cache for that job (including the 14 MB LiDAR project list) but does not
re-geocode: the geocoder answer is cached for 30 days.

Every HTTP call in a job is bound to the job deadline and the footprint stage has its own cap. As a backstop a
watchdog marks a job `timeout` 30 seconds after its deadline even if its thread is stuck.

### 1.3 Debug mode

Only with `ROOF_MEASURE_DEBUG=1`, never in production. The request accepts `method: "fixture"` with `fixture`
(a saved envelope or model, by file name with or without `.json`), `blocks_fixture` (skip the data stages and use a
saved blocks file) and `solar_fixture` (a saved Solar response for `solar_agent`); `GET /fixtures` and
`GET /fixtures/{name}` list and return the files in the fixtures directory. Outside debug mode these fields are
a 422 and the routes and the OpenAPI schema do not exist. Fixture jobs are not cached across fixtures: the fixture
names are part of the cache key.

## 2. Envelope `bond.roof_model/0.2`

The `result` of a done job. Parsers ignore unknown keys and tolerate missing optional ones.

- `contract`, `pipeline_version`, `method_used` (`lidar_skeleton`, `lidar_agent` or `solar_agent`; `auto` resolves
  to one of them), `footprint_source` (`lariac`, `osm`, `solar`, `lidar_hull`), `generated_at` (UTC).
- `model`: the unchanged 0.1 model, possibly merged by the verifier. It is always the final model.
- `totals`: exactly 14 keys, all derived from `model.totals` and `model.facets` by one function:
  `area_sqft`, `squares`, `eave_ft`, `rake_ft`, `ridge_ft`, `hip_ft`, `valley_ft`, `step_flashing_ft`,
  `predominant_pitch` (rise over 12, flat is 0), `facets` (count), and the four variants
  `drip_edge_eave_ft` (eave), `drip_edge_eave_rake_ft` (eave + rake), `ridge_cap_ridge_ft` (ridge),
  `ridge_cap_ridge_hip_ft` (ridge + hip).
- `verification`: `verdict`, `notes[]`, `adjustments[]`, `original_totals` (same keys as `totals`, before any
  merge), `model` (the verifier model id, or null), `rounds`, `usage {input_tokens, output_tokens}`.
- `confidence`: 0 to 1, see 2.2. `warnings[]`: English strings. `warning_codes[]`: same length and order.

### 2.1 Verdict

- `pass`: nothing moved.
- `adjusted`: the verifier merged runs of tiny, nearly collinear segments and recomputed; some total moved by more
  than 0.05 ft or 0.5 sq ft, or the predominant pitch or the facet count changed, and none moved past the fail limits.
- `fail`: total area moved by more than 5 percent, or any single edge-type total whose original length was over 10 ft
  moved by more than 10 percent.
- `unverified`: no verifier key, an API error, a timeout, or no final answer. The deterministic merge still ran and
  `model` is final. A verifier problem never fails the job. With `verify: false` neither the verifier nor the
  deterministic merge runs: `model` is the raw pipeline model and `verification.notes` says it was not requested.

A footprint from `solar` or `lidar_hull` can never be `pass`: it is lowered to `adjusted` with a note.

### 2.2 Confidence

Start from `model.confidence.overall` (high 0.9, medium 0.7, low 0.5). Cap at 0.85 for `osm` and at 0.5 for `solar`
and `lidar_hull`. Then `fail` takes the minimum with 0.3, `unverified` the minimum with 0.7, `adjusted` subtracts
0.05. LiDAR density below 12 points per square metre subtracts 0.1. Clamp to [0, 1] and round to two decimals.

### 2.3 Warning codes

Closed list, one per `warnings[]` entry. Unknown codes are kept as strings by parsers; the service emits `other`
for anything not listed.

| Code | Meaning |
|---|---|
| `footprint_osm` | footprint from OpenStreetMap (no parcel data) |
| `footprint_solar` | footprint estimated from Google Solar roof segments |
| `footprint_lidar_hull` | footprint derived from the LiDAR point cloud |
| `parcel_without_building` | the parcel matched but the county layer has no building |
| `other_buildings_on_parcel` | more than one building outline on the parcel; the largest was measured |
| `low_point_density` | LiDAR density below 8 points per square metre (the job fails below 4) |
| `method_fallback` | LiDAR failed and `solar_agent` was used under `auto` |
| `verifier_unverified` | the verifier did not review the result |
| `verifier_adjusted` | the verifier merged segments |
| `verifier_failed` | the verifier's fail rule tripped |
| `verifier_timeout` | reserved, not emitted yet (a verifier timeout is reported as `verifier_unverified`) |
| `solar_segments_only` | geometry comes from Solar segments, not LiDAR |
| `flat_roof_assumed` | reserved, not emitted yet |
| `other` | anything else |

### 2.4 Example

This is `fixtures/roof_measurement_0.2_pass.json`, verbatim. It is synthetic: a 35 by 26 ft hip at 4/12 at a
placeholder address. Copy it as an app's mock fixture.

```json
{
 "contract": "bond.roof_model/0.2",
 "pipeline_version": "0.2.0",
 "method_used": "lidar_skeleton",
 "footprint_source": "osm",
 "generated_at": "2026-11-10T00:00:00Z",
 "model": {
  "schema": "bond.roof_model/0.1",
  "generated_at": "2026-11-10T00:00:00Z",
  "address": {
   "line1": "100 Example Ave",
   "city": "Sampletown",
   "state": "CA",
   "zip": "90000",
   "formatted": "100 Example Ave, Sampletown, CA 90000"
  },
  "origin": {
   "lat": 0.0,
   "lng": 0.0
  },
  "north_deg": 0,
  "units": "ft",
  "source": {
   "method": "fixture",
   "footprint": {
    "provider": "synthetic",
    "id": "Synthetic hip 35 x 26 ft at 4/12",
    "area_sqft": 910.0
   },
   "lidar": null,
   "solar": null
  },
  "blocks": [
   {
    "id": "b1",
    "form": "hip",
    "polygon": [
     [
      0.0,
      0.0
     ],
     [
      35.0,
      0.0
     ],
     [
      35.0,
      26.0
     ],
     [
      0.0,
      26.0
     ]
    ],
    "pitch_rise": 4.0,
    "ridge_azimuth_deg": 90.0,
    "gable_edges": [],
    "eave_height_ft": 10.0,
    "plan_area_sqft": 910.0
   }
  ],
  "facets": [
   {
    "id": "f1",
    "block": "b1",
    "kind": "sloped",
    "polygon": [
     [
      22.0,
      13.0
     ],
     [
      13.0,
      13.0
     ],
     [
      0.0,
      0.0
     ],
     [
      35.0,
      0.0
     ]
    ],
    "pitch_rise": 4.0,
    "aspect_deg": 180.0,
    "plan_area_sqft": 286.0,
    "area_sqft": 301.47047
   },
   {
    "id": "f2",
    "block": "b1",
    "kind": "sloped",
    "polygon": [
     [
      22.0,
      13.0
     ],
     [
      35.0,
      0.0
     ],
     [
      35.0,
      26.0
     ]
    ],
    "pitch_rise": 4.0,
    "aspect_deg": 90.0,
    "plan_area_sqft": 169.0,
    "area_sqft": 178.14164
   },
   {
    "id": "f3",
    "block": "b1",
    "kind": "sloped",
    "polygon": [
     [
      13.0,
      13.0
     ],
     [
      22.0,
      13.0
     ],
     [
      35.0,
      26.0
     ],
     [
      0.0,
      26.0
     ]
    ],
    "pitch_rise": 4.0,
    "aspect_deg": 0.0,
    "plan_area_sqft": 286.0,
    "area_sqft": 301.47047
   },
   {
    "id": "f4",
    "block": "b1",
    "kind": "sloped",
    "polygon": [
     [
      13.0,
      13.0
     ],
     [
      0.0,
      26.0
     ],
     [
      0.0,
      0.0
     ]
    ],
    "pitch_rise": 4.0,
    "aspect_deg": 270.0,
    "plan_area_sqft": 169.0,
    "area_sqft": 178.14164
   }
  ],
  "edges": [
   {
    "id": "e1",
    "type": "eave",
    "points": [
     [
      0.0,
      0.0
     ],
     [
      35.0,
      0.0
     ]
    ],
    "length_ft": 35.0,
    "facets": [
     "f1"
    ]
   },
   {
    "id": "e2",
    "type": "eave",
    "points": [
     [
      35.0,
      0.0
     ],
     [
      35.0,
      26.0
     ]
    ],
    "length_ft": 26.0,
    "facets": [
     "f2"
    ]
   },
   {
    "id": "e3",
    "type": "eave",
    "points": [
     [
      35.0,
      26.0
     ],
     [
      0.0,
      26.0
     ]
    ],
    "length_ft": 35.0,
    "facets": [
     "f3"
    ]
   },
   {
    "id": "e4",
    "type": "eave",
    "points": [
     [
      0.0,
      26.0
     ],
     [
      0.0,
      0.0
     ]
    ],
    "length_ft": 26.0,
    "facets": [
     "f4"
    ]
   },
   {
    "id": "e5",
    "type": "hip",
    "points": [
     [
      22.0,
      13.0
     ],
     [
      35.0,
      0.0
     ]
    ],
    "length_ft": 18.88856,
    "facets": [
     "f1",
     "f2"
    ]
   },
   {
    "id": "e6",
    "type": "ridge",
    "points": [
     [
      13.0,
      13.0
     ],
     [
      22.0,
      13.0
     ]
    ],
    "length_ft": 9.0,
    "facets": [
     "f1",
     "f3"
    ]
   },
   {
    "id": "e7",
    "type": "hip",
    "points": [
     [
      0.0,
      0.0
     ],
     [
      13.0,
      13.0
     ]
    ],
    "length_ft": 18.88856,
    "facets": [
     "f1",
     "f4"
    ]
   },
   {
    "id": "e8",
    "type": "hip",
    "points": [
     [
      22.0,
      13.0
     ],
     [
      35.0,
      26.0
     ]
    ],
    "length_ft": 18.88856,
    "facets": [
     "f2",
     "f3"
    ]
   },
   {
    "id": "e9",
    "type": "hip",
    "points": [
     [
      13.0,
      13.0
     ],
     [
      0.0,
      26.0
     ]
    ],
    "length_ft": 18.88856,
    "facets": [
     "f3",
     "f4"
    ]
   }
  ],
  "holes": [],
  "totals": {
   "total_area_sqft": 959.22422,
   "pitched_area_sqft": 959.22422,
   "flat_area_sqft": 0,
   "predominant_pitch_rise": 4.0,
   "predominant_pitch_area_sqft": 959.22422,
   "squares": 9.59224,
   "lengths_ft": {
    "eave": 122.0,
    "rake": 0.0,
    "ridge": 9.0,
    "hip": 75.55425,
    "valley": 0.0,
    "step_flashing": 0.0,
    "wall_flashing": 0.0,
    "parapet": 0.0,
    "transition": 0.0,
    "unspecified": 0.0
   }
  },
  "confidence": {
   "overall": "medium",
   "notes": [
    "Wall flashing is not derivable from this data (0 ft here): LiDAR resolves no wall steps and skylight/curb openings are not modelled.",
    "Total area includes the roof overhang beyond the county wall line (blocks may extend up to 1 m past the footprint)."
   ]
  },
  "warnings": [],
  "debug": {}
 },
 "totals": {
  "area_sqft": 959.224,
  "squares": 9.592,
  "eave_ft": 122.0,
  "rake_ft": 0.0,
  "ridge_ft": 9.0,
  "hip_ft": 75.554,
  "valley_ft": 0.0,
  "step_flashing_ft": 0.0,
  "predominant_pitch": 4.0,
  "facets": 4,
  "drip_edge_eave_ft": 122.0,
  "drip_edge_eave_rake_ft": 122.0,
  "ridge_cap_ridge_ft": 9.0,
  "ridge_cap_ridge_hip_ft": 84.554
 },
 "verification": {
  "verdict": "pass",
  "notes": [
   "Synthetic example: edge lengths and areas agree."
  ],
  "adjustments": [],
  "original_totals": {
   "area_sqft": 959.224,
   "squares": 9.592,
   "eave_ft": 122.0,
   "rake_ft": 0.0,
   "ridge_ft": 9.0,
   "hip_ft": 75.554,
   "valley_ft": 0.0,
   "step_flashing_ft": 0.0,
   "predominant_pitch": 4.0,
   "facets": 4,
   "drip_edge_eave_ft": 122.0,
   "drip_edge_eave_rake_ft": 122.0,
   "ridge_cap_ridge_ft": 9.0,
   "ridge_cap_ridge_hip_ft": 84.554
  },
  "model": "claude-sonnet-5-5",
  "rounds": 1,
  "usage": {
   "input_tokens": 8200,
   "output_tokens": 310
  }
 },
 "confidence": 0.7,
 "warnings": [
  "Footprint from OpenStreetMap; parcel data unavailable outside Los Angeles County."
 ],
 "warning_codes": [
  "footprint_osm"
 ]
}
```

## Appendix A. Environment variables

| Var | Required | Default | Meaning |
|---|---|---|---|
| `PORT` | no (Railway sets it) | 8011 | listen port |
| `ROOF_MEASURE_TOKEN` | yes | none | bearer token, at least 32 characters; the process refuses to start without it |
| `ROOF_MEASURE_AUTH` | no | `on` | `off` only with a loopback `ROOF_MEASURE_HOST` (local dev) |
| `ROOF_MEASURE_HOST` | no | `::` | bind host; `::` is IPv6-only under uvicorn (right for Railway), so local Docker needs `0.0.0.0` |
| `DATA_DIR` | no | `<service>/data` | jobs and results; `/data` on a Railway volume |
| `ROOF_MEASURE_CACHE` | no | `<service>/cache` | HTTP fetch cache (LiDAR tiles, geocode); `/data/cache` on Railway |
| `ROOF_MEASURE_WORKERS` | no | 2 | worker pool size |
| `ROOF_MEASURE_QUEUE_MAX` | no | 10 | jobs allowed to wait before 429; 0 means no waiting (a job is admitted only when a worker is free) |
| `ROOF_MEASURE_JOB_TIMEOUT_S` | no | 180 | per-job deadline |
| `ANTHROPIC_API_KEY` | no | none | enables the LLM verifier and the agent methods; absent means `unverified` |
| `GOOGLE_SOLAR_API_KEY` | no | none | enables the Solar footprint link and `solar_agent` |
| `ROOF_MEASURE_OVERPASS_URLS` | no | three official overpass-api.de hosts | comma separated Overpass mirrors, all asked in parallel, first answer wins (45 s each) |
| `ROOF_MEASURE_FOOTPRINT_S` | no | 60 | cap on the footprint stage within the job timeout |
| `ROOF_MEASURE_FIXTURES` | no | repo `fixtures/`, else `/app/fixtures` | directory of the debug fixtures; the image sets `/app/fixtures` |
| `ROOF_MEASURE_JOB_RETENTION_DAYS` | no | 14 | finished job directories and cached results older than this are deleted (jobs after each job and at boot, results at boot); the fetch cache is purged after 30 days |
| `RAILWAY_RUN_UID` | Railway only | none | set to `0`: the volume is root-owned, so the container then runs as root |
| `ROOF_MEASURE_DEBUG` | no | unset | `1` enables fixture routes and fixture request fields (never in production) |
| `ROOF_MEASURE_CORS_ORIGIN_REGEX` | no | localhost | CORS allow regex |
| `ROOF_MEASURE_NETWORK` | tests only | unset | `1` runs network-marked tests |

Run one replica only: the job store is on the local volume.

## Appendix B. Label keys

The Dart packages draw every user-visible string from a `RoofLabels` object with English defaults. An app builds it
from its own strings with `RoofLabels.fromMap(Map<String, String>)`; unknown keys are ignored. Service text
(`warnings`, `verification.notes`, `confidence.notes`) stays English: map `warning_codes` instead.

There are 82 keys. An app passes a `Map<String, String>` to `RoofLabels.fromMap`: missing keys keep the English
default and unknown keys are ignored. Template keys take `{name}` placeholders that the package fills in
(for example `source_method` takes `{method}`). The parser records every unknown value it maps (edge type, facet
kind, block form, `lengths_ft` key) in `RoofModel.parseNotes` instead of throwing. `verification.model` is always
present in the envelope and is null when the result is unverified.

| Key | Placeholders | Group |
|---|---|---|
| `legend_eave` |  | Legend names (one per edge type) |
| `legend_rake` |  | Legend names (one per edge type) |
| `legend_ridge` |  | Legend names (one per edge type) |
| `legend_hip` |  | Legend names (one per edge type) |
| `legend_valley` |  | Legend names (one per edge type) |
| `legend_step_flashing` |  | Legend names (one per edge type) |
| `legend_wall_flashing` |  | Legend names (one per edge type) |
| `legend_parapet` |  | Legend names (one per edge type) |
| `legend_transition` |  | Legend names (one per edge type) |
| `legend_unspecified` |  | Legend names (one per edge type) |
| `length_title` |  | Diagram titles and captions |
| `length_caption` |  | Diagram titles and captions |
| `area_title` |  | Diagram titles and captions |
| `area_caption` |  | Diagram titles and captions |
| `summary_caption` |  | Diagram titles and captions |
| `summary_page_title` |  | Diagram titles and captions |
| `address_missing` |  | Diagram titles and captions |
| `total_area` |  | Totals rows and headings |
| `squares` |  | Totals rows and headings |
| `pitched_area` |  | Totals rows and headings |
| `flat_area` |  | Totals rows and headings |
| `predominant_pitch` |  | Totals rows and headings |
| `facets` |  | Totals rows and headings |
| `edge_total` |  | Totals rows and headings |
| `confidence` |  | Totals rows and headings |
| `total_pitched_area` |  | Totals rows and headings |
| `total_flat_area` |  | Totals rows and headings |
| `predominant_pitch_area` |  | Totals rows and headings |
| `two_story_area` |  | Totals rows and headings |
| `two_layer_area` |  | Totals rows and headings |
| `unspecified_pitch_area` |  | Totals rows and headings |
| `not_available` |  | Totals rows and headings |
| `pitch_flat` |  | Totals rows and headings |
| `unit_ft` |  | Units |
| `unit_in` |  | Units |
| `unit_sqft` |  | Units |
| `unit_squares` |  | Units |
| `source_heading` |  | Source and data lines |
| `source_method` | `{method}` | Source and data lines |
| `source_footprint` | `{provider}` | Source and data lines |
| `footprint_id` | `{id}` | Source and data lines |
| `footprint_area` | `{area}` | Source and data lines |
| `source_lidar` | `{project}`, `{date}` | Source and data lines |
| `lidar_points` | `{n}` | Source and data lines |
| `source_solar` | `{date}`, `{quality}` | Source and data lines |
| `solar_segments` | `{n}` | Source and data lines |
| `model_generated` | `{date}` | Source and data lines |
| `unknown` |  | Source and data lines |
| `method_lidar_skeleton` |  | Method names |
| `method_lidar_agent` |  | Method names |
| `method_solar_agent` |  | Method names |
| `method_manual` |  | Method names |
| `method_fixture` |  | Method names |
| `confidence_notes_heading` |  | Notes, warnings, footers, compass, PDF title |
| `warnings` |  | Notes, warnings, footers, compass, PDF title |
| `excluded_openings_heading` |  | Notes, warnings, footers, compass, PDF title |
| `excluded_from_areas` | `{items}` | Notes, warnings, footers, compass, PDF title |
| `footer_length` |  | Notes, warnings, footers, compass, PDF title |
| `footer_area` |  | Notes, warnings, footers, compass, PDF title |
| `compass_north` |  | Notes, warnings, footers, compass, PDF title |
| `pdf_title` |  | Notes, warnings, footers, compass, PDF title |
| `action_print` |  | Actions and status lines |
| `action_save_pdf` |  | Actions and status lines |
| `action_share_pdf` |  | Actions and status lines |
| `status_preparing_print` |  | Actions and status lines |
| `status_printed` |  | Actions and status lines |
| `status_building_pdf` |  | Actions and status lines |
| `status_saved` |  | Actions and status lines |
| `status_sharing_pdf` |  | Actions and status lines |
| `status_shared` |  | Actions and status lines |
| `status_failed` | `{error}` | Actions and status lines |
| `totals_heading` |  | Totals variants, verification, verdicts |
| `variant_drip_edge_eave` |  | Totals variants, verification, verdicts |
| `variant_drip_edge_eave_rake` |  | Totals variants, verification, verdicts |
| `variant_ridge_cap_ridge` |  | Totals variants, verification, verdicts |
| `variant_ridge_cap_ridge_hip` |  | Totals variants, verification, verdicts |
| `verification` |  | Totals variants, verification, verdicts |
| `verdict_pass` |  | Totals variants, verification, verdicts |
| `verdict_adjusted` |  | Totals variants, verification, verdicts |
| `verdict_fail` |  | Totals variants, verification, verdicts |
| `verdict_unverified` |  | Totals variants, verification, verdicts |
| `generated` |  | Totals variants, verification, verdicts |

## Appendix C. Fixtures

All under `fixtures/`, all at most 100 KB, placeholder address `100 Example Ave, Sampletown, CA 90000`, origin 0/0.
Regenerate with `make -C services/roof_measure fixtures`.

| File | What it is |
|---|---|
| `roof_measurement_0.2_pass.json` | envelope, synthetic hip, verdict `pass`, footprint `osm` |
| `roof_measurement_0.2_adjusted.json` | envelope, hip with a bowed south eave merged by the verifier, `adjusted` |
| `roof_measurement_0.2_unverified.json` | envelope, synthetic gable, `unverified`, footprint `lariac` |
| `roof_measurement_0.2_fail.json` | envelope, synthetic hip, `fail` (the original area is forced 8 percent off; not a real measurement) |
| `synthetic_flat_curbs.json` | 0.1 model: flat roof with parapet, 17 chimney curbs as holes with wall flashing, one step flashing edge |
| `synthetic_hip_zigzag.json` | 0.1 model: the hip with a seven-segment south eave; the verifier's merge input |
| `synthetic_solar_response.json` | a Google Solar `buildingInsights`-shaped response (service input, not a model) |
