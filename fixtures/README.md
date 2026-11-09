# Fixtures

Site 1 is a real roof. Its address and coordinates are not tracked: the fixtures carry the placeholder
address `100 Example Ave, Sampletown, CA 90000` and origin 0/0. The real values live in `local/sites.json`
(copy `services/roof_measure/tests/sites.example.json`), and the property data tests need (point clouds,
parcel and census recordings) lives in `local/test-data/`. Tests that need either skip when it is absent.

Contract: `docs/contracts/roof_model.md` (schema `bond.roof_model/0.1`).

| File | What it is | Owner |
|---|---|---|
| `site1_truth.json` | Manual digitisation of the Roofr length and area reports for site 1 (a real roof; address and coordinates in `local/sites.json`, not tracked) (`source.method: "manual"`). The reference a service run is compared against. | manual digitisation |
| `solar_site1_fixture.json` | SYNTHETIC Google Solar `buildingInsights` response for the same building, hand-written from the Roofr numbers. Not a Google response; replace with a live one once the Solar API is enabled. The original note is kept as `_note_original`. | manual digitisation |
| `site1_lidar.json` | What the LiDAR service produced for the same address. | service |
| `site1_blocks.json` | Intermediate `bond.roof_blocks/0.1` output of the data layer (LiDAR blocks) for the same address. NOT a roof model. Any code that loads every fixture must filter by the `schema` string, as the Dart tests and the demo already do. | service |
| `synthetic_hip.json`, `synthetic_gable.json`, `synthetic_flat_parapet.json` | Closed-form cases with known totals, produced by the service (`python -m roof_measure.synth`). | service |
| `sync/upload_request_ok.json` | Valid upload body: a put, a patch, a put and a delete on `notes`. | hand-written |
| `sync/upload_request_mixed.json` | Upload body that yields every verdict kind (ok, invalid, skipped, conflict, not_found, unsupported). Needs a `note-taken` row owned by another user. | hand-written |
| `sync/upload_response_mixed.json` | The exact answer to the mixed request. | hand-written |
| `sync/upload_response_all_codes.json` | Shape fixture: one result per verdict code, including `resolved_id`. For client parsers. | hand-written |
| `sync/upload_request_too_many_ops.json` | 101 ops: refused with a 422. | generated |
| `sync/upload_request_dup_seq.json` | Two ops with the same `seq`: refused with a 422. | hand-written |
| `sync/bad_ids.json` | Id strings with the expected result: accepted, an `invalid` verdict, or a 422. | hand-written |
| `sync/sync_token_claims.json` | Sync token header, claims, token response, the `sync_off` body, and an example token signed by the test key. TEST ONLY. | generated |
| `sync/jwks_example.json` | Public half of the throwaway EC P-256 test key that signed the example token. TEST ONLY. | generated |

Contract for the sync files: `docs/contracts/sync_upload.md`.

## site1_truth.json: accuracy caveats

- The plan is reconstructed from photographs of the printed pages. Shape error is 3 to 5 percent and the
  polygons are not orthogonalised; facet polygons do not tile their neighbours exactly.
- `totals` are the PRINTED numbers, not recomputed. Edge sums and facet sums differ slightly (table below).
- Facet `area_sqft` is the printed Roofr area. `plan_area_sqft` is the reconstructed polygon area minus the
  openings inside it. They differ by up to 10 percent (Flat 922 includes an unlabelled lobe), so
  `area_sqft` is not `plan_area_sqft` times the slope factor here.
- Hip pitch is not printed. This fixture uses 3.9/12 (LiDAR plane fit); the research derived about 5/12
  (range 4.5 to 6.5). Awnings are sloped, pitch unknown, set to 3.9/12.
- The 17 dashed openings are holes of kind `chimney` (curbs), so their outlines carry 16 `wall_flashing` and
  1 `step_flashing` edge. Skylight vs curb is not distinguishable in the photo.
- Not represented: about 100 ft of wall flashing and about 38 ft of step flashing (not visible in the
  drawing), two-story and two-layer areas (0 in the report, not measured), roofing material, parapet and wall
  heights (`eave_height_ft` is null). `confidence.notes` and `warnings` in the file list every uncertain reading.
- Because of the above, a totals-recompute test on this file needs tolerances: areas 3 percent, lengths 5
  percent for eave, hip, ridge, rake and parapet; wall and step flashing are expected to fall short.

## Regenerate

```
python3 -m venv .venv && .venv/bin/pip install shapely
.venv/bin/python -I fixtures/tool/truth_from_research.py \
    --research docs/research/2026-11-07-roof-poc/ground-truth --out fixtures/site1_truth.json
```

The script prints the check table and exits non-zero when a check fails (ten length keys, two-point edges
with positive length, eave/hip/ridge/rake/parapet within 10 percent of printed, facet area sum 5405 +- 10,
valid closed polygons).

## Printed Roofr truth for site 1

Length report (page 3), with the sum of edges in the fixture:

| Type | Printed | ft | Fixture edge sum |
|---|---|---|---|
| Eaves | 209 ft 8 in | 209.67 | 208.0 |
| Ridges | 7 ft 9 in | 7.75 | 7.75 |
| Hips | 76 ft 2 in | 76.17 | 78.0 |
| Rakes | 32 ft 0 in | 32.00 | 30.5 |
| Parapet wall | 423 ft 10 in | 423.83 | 416.1 |
| Wall flashing | 344 ft 5 in | 344.42 | 232.4 (partly located) |
| Step flashing | 50 ft 0 in | 50.00 | 11.4 (partly located) |
| Valleys, transitions, unspecified | 0 | 0 | 0 |

Area report (page 4), square feet:

| Item | Printed |
|---|---|
| Total roof area | 5405 (54.05 squares) |
| Pitched | 1200 |
| Flat | 4205 |
| Two-story, two-layer, unspecified pitch | 0 |
| Predominant pitch | 0/12 over 4205 |

Facets: hip 300 (N), 169 (W), 190 (E), 289 (S); flats 151, 2,121, 1,013, 922; awnings 82, 87, 86. The facet
labels add up to 5410 (rounded up), 5 above the printed total.
