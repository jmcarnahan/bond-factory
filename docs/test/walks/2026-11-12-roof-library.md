# Roof library walk (2026-11-12)

What was walked: the `roof-library` branch (plan `local/plan/2026-11-11-roof-library`, phases 1–2: library facade,
config Runtime, lazy imports, `service`/`render` extras) through the roof demo, to confirm the SERVICE path still
works end to end after the refactor; commit bcc303d (clean), per `docs/test/WEB.md` "Web walk recipe: demos/roof_demo",
by Sonnet walkers with the Playwright test runner (headless Chromium, specs under `tmp/handtest`, deleted at cleanup).
Stack: roof_measure on :8011 (auth off on loopback, debug on, DATA_DIR `tmp/walk-data`, started from the branch),
roof demo debug web-server on :8077 with `ROOF_SERVICE=http://localhost:8011`. Phone on web: the same demo at
390x844 (plain viewport). Simulator: not booted.
Shots pass: skipped: no `make shots` target.
Library examples (director, module venv): the service README "Use as a library" example (with the documented offline
additions) and the contract §3.10 snippet both returned a `bond.roof_model/0.2` envelope with the fixture's totals.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| 01 load | none | PASS | heading "Roof measurement demo" (tab title "Roof demo"), address field, method segments labelled Auto / LiDAR / LiDAR + agent / Solar + agent, Measure, EN/ES, ten fixture chips |
| 02 pass envelope | none | PASS | canvas, drip edge (eave only / eave + rake) and ridge cap (ridge only / ridge + hip) rows, "Verified - Synthetic example…", Generated line, Print / Save PDF / Share PDF |
| 03 Spanish | none | PASS | "Aleros", scrollWidth 1280; EN restores "Eaves" |
| 04 Save PDF / Print | none | PASS / SKIP | `roof-report.pdf` 11,823 bytes; Print SKIP: headless Chromium, no printing iframe appeared |
| 05 adjusted / fail / unverified | none | PASS | "Adjusted after review - Merged 7 eave segments…", "Failed verification - SYNTHETIC FIXTURE…", "Not verified - Unverified: no ANTHROPIC_API_KEY…" |
| 06 GET /fixtures | none | PASS | 200, list includes roof_measurement_0.2_pass; no "(service)" chips (all bundled, expected) |
| 07 live job (the NY spike site, method LiDAR) | none | PASS | running at 1 s, report at 5 s ("queued" too brief to catch); 4,366 sq ft, 43.66 squares, 41 facets, "Not verified" (no key); service log `stage=done footprint_source=osm cache_hit=false ms=1856`, no traceback (lazy imports, config and render flag all exercised on the service path) |
| 08 pass chip after the job | none | PASS | the chip's report replaced the live one |
| 09 error check | none | PASS | 0 dialogs, 0 console errors, 0 pageerrors |
| Dialogs/popups on every page visited | | 0 | |

## Phone (390x844, plain viewport)
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 01 load | phone-web | none | PASS | scrollWidth 390; all controls reachable |
| 02 pass compact | phone-web | none | PASS | compact layout, two-column legend, paired variant rows, verdict and Generated lines; director read the scrolled screenshot: legible |
| 03 Spanish | phone-web | none | PASS | no overflow (legend names short: ellipsis not exercised) |
| 04 dense fixture (site1_lidar) | phone-web | none | PASS | compact layout, scrollWidth 390 |
| 05 fail line wraps | phone-web | none | PASS | six lines inside 390 px |
| 06 Save PDF | phone-web | none | PASS | 11,823-byte vector PDF |
| 07 text scale | phone-web | none | SKIP | no text-scale switch in the demo |
| Console / runtime errors, popups | | | clean, 0 | |

Previous walk's open items (2026-11-11-roof-module-v1): none were open (P1 and W3 fixed in that round; W1 recipe
corrected). Re-walked PASS here: compact legibility (P1), chip after a job (W3 in reverse).

Defects:
- W1 (copy, recipe): the recipe named the method segments by their raw values; the demo labels them Auto / LiDAR /
  LiDAR + agent / Solar + agent. Recipe corrected in this round.
- W2 (copy, minor): the browser tab title is "Roof demo", the heading "Roof measurement demo". Recipe clarified.
- P1 (minor, not a defect): the accessibility overlay reports one 10 px node; rendered canvas text is legible at
  12 px or more in the screenshot. P2: Spanish ellipsis not exercised (short labels).

Timing: web lane about 20 minutes (two runs, the second only steps 07–09) and ~40 Playwright calls; phone lane about
10 minutes. Live-job screenshots were deleted by the walker because they showed the site address.
