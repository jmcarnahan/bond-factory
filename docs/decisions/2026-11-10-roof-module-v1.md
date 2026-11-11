# Roof module v1 (2026-11-10)

Context: the roof POC (see `2026-11-07-roof-poc-summary.md`) becomes a module the consumer apps can pin. v1 adds a job-based
service API, national footprint coverage, an adversarial verifier, a 0.2 envelope (`docs/contract-0.2.md`) and a Dart
envelope class, label overrides, totals variants and on-device PDF. The same change removes third-party report data
and real-site details from the tree and adds a licence. Dated and append-only; later changes get a new file.

## Decisions

- D1 The verifier never fails a job: any error gives `unverified` with the deterministic result; `fail` only when
  area moves more than 5% or one edge-type total moves more than 10%.
- D2 One shared `Deadline` budgets the pipeline (footprint stage 60 s, see D18; job 180 s); the 90 s figure is a spike target.
- D3 Jobs live on disk (`DATA_DIR/jobs/<id>`), single replica, bounded pool and queue; boot marks old jobs `interrupted`.
- D4 The cache key is the geocoder output (or rounded coordinates), plus method, verify, pipeline version and key presence.
- D5 Auth fails closed (constant-time bearer compare, refuse to start without a token); debug surfaces only with `ROOF_MEASURE_DEBUG=1`.
- D6 Degraded footprint sources (Solar hull, LiDAR hull) never reach `pass`; confidence is capped at 0.5.
- D7 `RoofModel` keeps its API; the parser became tolerant (unknown edge, facet, form and `lengths_ft` values map with `parseNotes`) and `model.dart` was split into model, model_parts and totals; `RoofMeasurement.fromJson` and `parseAny` read the envelope; totals variants are computed in Dart.
- D8 Labels are a `RoofLabels` object with English defaults, built from a plain map; no l10n system in the packages.
- D9 Hygiene scope: third-party report data, real-site strings and the brand name leave tracked files; the gate learns addresses and coordinates.
- D10 The whole repo is GPL-3.0-or-later (see below).
- D11 Scrub order: build, review, John merges, history rewrite in a fresh mirror, force push, consumers re-pin.
- D12 `auto` method is `lidar_skeleton`, falling back to `solar_agent` only on no or sparse LiDAR with both keys set.
- D13 Spike coordinates are never tracked; the tracked table records state, source, project, density, seconds, outcome.
- D14 `error` is an object `{code, message, retryable}`.
- D15 No PDAL: LiDAR is laspy and lazrs over HTTPS; the image needs CGAL only through the compas_cgal wheel.
- D16 The envelope carries `warning_codes[]` parallel to `warnings[]`; parsers tolerate unknown codes.
- D17 LiDAR density floor is 4 pts/m²; below 8 pts/m² the job carries a `low_point_density` warning.
- D18 All Overpass mirrors are fired in parallel, 45 s each, inside a 60 s footprint stage; the official overpass-api.de hosts are the default and `ROOF_MEASURE_OVERPASS_URLS` overrides them.

## Licence

GPL-3.0-or-later for the whole repository, chosen by John on 2026-11-11 ("make it gpl 3 for now"). The roof service
links compas_cgal. compas_cgal declares LGPL-3, and the CGAL Straight_skeleton_2 component it wraps is GPL per the CGAL
documentation. One licence for everything is simpler than a per-module split. The service is deployed, not
distributed. `LICENSE` holds the text, `NOTICE` the reason, the root README has a Licensing paragraph, and the service's
pyproject declares `license = "GPL-3.0-or-later"`. GPL-3 also covers the Dart packages that the apps pin by git, so each app's own licensing has to account for it; this is why the choice is marked "for now". The choice may change later, and no claim is made that it is legally
sufficient. The Roboto font keeps its Apache-2.0 licence.

## Hygiene changes

- Removed the digitised third-party report, the two fixtures hand-derived from it, the script that built them and the
  research `ground-truth/` folder. Synthetic fixtures replace them (`fixtures/README.md`).
- Redacted real-site fingerprints, a test coordinate and a city name in `docs/`; the third-party brand became "the
  third-party report" or "commercial report".
- `tool/public_hygiene.sh` now also flags US street addresses, Southern-California coordinate pairs, any lat/lng key
  with five or more decimals and the brand word, and it scans `docs/research`. `tool/allowlist_hygiene.txt` gained
  a `text:` entry for the `Example Ave` placeholder.
- Run the scan with `--worktree` before a commit to see untracked files too.

## History

Before 2026-11-11 the git history contained third-party report data (a commercial measurement report, hand-digitised) and a real street
address. History was rewritten on 2026-11-11 (git-filter-repo, force push of `main`, dependabot branches deleted).
Commit SHAs from before the rewrite are void: re-pin to the new `main` head and treat any old SHA as untrusted. Map
for the pins consumers held: 4b26615 → 59055d7e3580a556766cc1879aaa5834ecb2c78c, 3d7b280 →
f842c5e7d441a358da244a2b8e83d4d9f7d050a7, de681b4 → 117e8cc4b3c8712354ef27d37a789973c06e46b9; the roof module merge
(old fad8722) is b8ce2e13e91502c4922c8099897c8c62c1f46763.

## Scrub runbook (summary; run only on John's explicit go)

1. Preconditions: the roof module is merged to `main`; a private mirror backup exists outside the repo.
2. Install git-filter-repo; clone a fresh `--mirror`.
3. Keep the replacement expressions file outside the repo (gitignored `local/scrub/`); it names the sensitive strings,
   so they never appear in tracked files.
4. Drop the removed paths from history and apply the replacements in the mirror; keep the commit map.
5. Verify: a history-wide grep for the sensitive strings is empty, and the hygiene gate passes on every commit tip.
6. Delete the dependabot branches and close their PRs, then force-push the mirror.
7. Ask GitHub Support to purge cached commits and pull refs; old SHAs stay fetchable until then.
8. Update the SHA noted in the sign-in migration doc under `docs/migration/`, then re-pin consumers (the sign-in consumer only before or after its cutover).
9. Everyone re-clones or hard-resets, clears the pub cache and re-runs `make hooks`.
10. Hand the new `main` SHA, `docs/contract-0.2.md` and the environment variable table to the roof-diagram consumer.
