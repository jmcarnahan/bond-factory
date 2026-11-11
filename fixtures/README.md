# Fixtures

Site 1 is a real roof. Its address and coordinates are not tracked: the fixtures carry the placeholder
address `100 Example Ave, Sampletown, CA 90000` and origin 0/0. The real values live in `local/sites.json`
(copy `services/roof_measure/tests/sites.example.json`), and the property data tests need (point clouds,
parcel and census recordings) lives in `local/test-data/`. Tests that need either skip when it is absent.

Contract: `docs/contracts/roof_model.md` (schema `bond.roof_model/0.1`; the service wraps it in the `0.2` envelope, see `docs/contract-0.2.md`).

| File | What it is | Owner |
|---|---|---|
| `roof_measurement_0.2_{pass,adjusted,unverified,fail}.json` | Example 0.2 envelopes, one per verification verdict. Each file IS the envelope (the `result` of the job GET response, `contract` is `bond.roof_model/0.2`) and its `model` is the 0.1 roof model; see `docs/contract-0.2.md`. The Appendix C list there covers only these roof envelopes; the bare models (`site1_*`, `synthetic_*`) remain separate. Asserted by the service and by `bond_roof` (Dart). | service |
| `synthetic_flat_curbs.json` | Closed-form flat block with a parapet, 17 chimney curbs (`wall_flashing` outlines) and one `step_flashing` edge. Keeps the chimney-hole tests. | service (`synth.py`) |
| `synthetic_hip_zigzag.json` | Closed-form hip whose south eave is split into 7 segments (five short ones under 2 ft between two 13 ft ends), nearly collinear. The verifier's `adjusted` input. | service (`synth.py`) |
| `synthetic_solar_response.json` | SYNTHETIC Google Solar `buildingInsights` response built by `synth.py`. Not a Google response. | service (`synth.py`) |
| `site1_lidar.json` | What the LiDAR service produced for the same address. | service |
| `site1_blocks.json` | Intermediate `bond.roof_blocks/0.1` output of the data layer (LiDAR blocks) for the same address. NOT a roof model. Any code that loads every fixture must filter by the `schema` string, as the Dart tests and the demo already do. | service |
| `synthetic_hip.json`, `synthetic_gable.json`, `synthetic_flat_parapet.json` | Closed-form cases with known totals, produced by the service (`python -m roof_measure.synth`). | service |
| `sync/upload_request_ok.json` | Valid upload body: a put, a patch, a put and a delete on `notes`. | hand-written |
| `sync/upload_request_mixed.json` | Upload body that yields every verdict kind (ok, invalid, skipped, conflict, not_found, unsupported). Needs a `note-taken` row owned by another user. | hand-written |
| `sync/upload_response_mixed.json` | The exact answer to the mixed request. | hand-written |
| `sync/upload_response_all_codes.json` | Shape fixture: one result per verdict code, including `resolved_id`. For client parsers. | hand-written |
| `signin/start_request_web.json`, `start_request_native.json`, `start_response.json` | Sign-in start bodies (web and native) and the `{url}` answer. Asserted by bond_signin (py and Dart) and the example. | hand-written |
| `signin/callback_redirects.json` | The four redirect shapes after a sign-in callback (web ok, web error, native return, native error). | hand-written |
| `signin/redeem_request.json`, `redeem_response.json` | Native hand-off redeem body and the session answer. | hand-written |
| `signin/refresh_request_body.json`, `refresh_response.json` | Body-delivery refresh request (refresh_token, rotation_id, delivery) and its answer. | hand-written |
| `signin/error_envelope.json`, `providers_payload.json`, `wanted_list.json`, `labels_codes.json` | Error body, `/auth/providers` with the sign-in keys, the `wanted` scope-set list, and the refusal-code list every client label table must cover. | hand-written |
| `signin/seed_identities.json` | The example's fake-mode identities (invited or not, provider, capabilities, wanted sets); asserted against the example's seeds by its tests, and the identities the walk signs in as. | hand-written |
| `sync/upload_request_too_many_ops.json` | 101 ops: refused with a 422. | generated |
| `sync/upload_request_dup_seq.json` | Two ops with the same `seq`: refused with a 422. | hand-written |
| `sync/bad_ids.json` | Id strings with the expected result: accepted, an `invalid` verdict, or a 422. | hand-written |
| `sync/sync_token_claims.json` | Sync token header, claims, token response, the `sync_off` body, and an example token signed by the test key. TEST ONLY. | generated |
| `sync/jwks_example.json` | Public half of the throwaway EC P-256 test key that signed the example token. TEST ONLY. | generated |
| `tasks/task.json` | One `TaskItem` as `GET /tasks/{id}` returns it (two checklist items, one link, a mirrored Google event, a 15-minute reminder). Round-tripped by `bond_tasks` (Dart) and `bond_tasks_py`. Keys: the `TaskItem` table in `packages/bond_tasks/README.md`; `libs/bond_tasks_py` pins the same list in `ITEM_KEYS`. | hand-written |

Contract for the sync files: `docs/contracts/sync_upload.md`.

## Ground truth

Synthetic fixtures only; no third-party report data is tracked. Expected totals come from the closed-form
geometry of each synthetic case.
