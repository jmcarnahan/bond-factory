# Roof module v1 walk (2026-11-11)

What was walked: phase 1 of `local/plan/2026-11-10-roof-module-v1` (0.2 envelope in the demo, label overrides
EN/ES, totals variants, compact phone layout, Print / Save / Share PDF, a live service job), commit edf5ee2 (dirty:
the walk-round fixes listed below were in the tree), per `docs/test/WEB.md` "Web walk recipe: demos/roof_demo"
(written for this walk), by Sonnet walkers with the Playwright test runner (headless Chromium, specs under
`tmp/handtest`, deleted at cleanup).
Stack: roof_measure on :8011 (auth off on loopback, debug on, DATA_DIR `tmp/walk-data`), roof demo debug web-server
on :8077 with `ROOF_SERVICE=http://localhost:8011`. Phone on web: the same demo at 390x844 (no separate target).
Simulator: not booted.
Shots pass: skipped: no `make shots` target.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| 01 load | none | PASS | title, address field, method segments, Measure, EN/ES, ten fixture chips |
| 02 pass envelope | none | PASS | canvas, totals 959 sq ft / 9.59 squares / 4 facets, drip edge 122 ft both, ridge cap 9 ft and 84 ft 7 in, "Verified - …" line, Generated line, Print / Save PDF / Share PDF |
| 03 Spanish | none | PASS | "Aleros", "Gotero (solo alero)", "Remate de cumbrera …"; no overflow at 1280; EN restores "Eaves" |
| 04 Save PDF / Print | none | PASS / SKIP | `roof-report.pdf` 11.8 KB, 3 pages, fonts embedded (vector; W2 withdrawn); Print SKIP: headless Chromium never fires `beforeprint`, the printing iframe was inserted |
| 05 adjusted / fail / unverified | none | PASS | "Adjusted after review - Merged 7 eave segments…", "Failed verification - SYNTHETIC FIXTURE…", "Not verified - Unverified: no ANTHROPIC_API_KEY…" |
| 06 service fixture chip | none | SKIP | no "(service)" chips: every service fixture is also bundled and the demo hides duplicates (recipe corrected) |
| 07 live job | none | PASS (director) | the walker's run hit a service process started before the last code edits (lazy ImportError); re-run by the director on the restarted service with the NY spike site: queued → running → done in 48 s, footprint osm, `unverified` (no key), 4,366 sq ft |
| 08 error check | none | PASS | 0 dialogs; the one page error ("Script error for web_entrypoint.dart") coincided with the demo restart and did not recur on a fresh load |
| Dialogs/popups on every page visited | | 0 | |

## Phone (390x844, plain viewport)
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 01 load | phone-web | none | PASS | scrollWidth 390; all controls reachable |
| 02 pass compact | phone-web | none | FAIL → PASS | first run: 800x1000 design at a 358 px card rendered 5–6 px labels (P1); after the fix (400x500 design, ≥ 12 px rendered) re-walked: legible, two-column legend, variant rows, verdict and Generated lines |
| 03 Spanish | phone-web | none | PASS | no overflow; long legend names ellipsised |
| 04 dense fixture (site1_lidar) | phone-web | none | PASS | compact layout, no overflow; many labels hidden by design |
| 05 fail line wraps | phone-web | none | PASS | five lines inside 390 px |
| 06 Save PDF | phone-web | none | PASS | 11.8 KB vector PDF |
| 07 text scale | phone-web | none | SKIP | no text-scale switch in the demo |
| Console / runtime errors, popups | | | clean, 0 | the "ViewInsets cannot be negative" assertion appears only under Playwright `isMobile`/`hasTouch` emulation (P3 withdrawn) |

Previous walk's open items: none for this surface (first walk of roof_demo).

Defects:
- P1 (major, fixed in this round): compact layout text 5–6 px at phone width. Fixed by a 400x500 compact design with
  every text ≥ 12 px rendered at a 358 px card; re-walked PASS.
- W3 (minor, fixed in this round): after a failed Measure the previously loaded fixture report stayed under the error
  line. Fixed: Measure clears the current report; a failure shows only the error line (widget test, not re-walked in
  the browser).
- W1 (minor, recipe): the "(service)" chip step does not exist when all fixtures are bundled; recipe corrected.
- W2 and P2 (withdrawn): the 20 KB PDF expectation was the brief's guess; the vector PDF is 11.8 KB with three pages.
- W4 and P3 (withdrawn): artifacts of the demo restart during the walk and of mobile emulation.

Timing: web lane about 25 minutes and ~60 Playwright calls (including the restart); phone lane about 12 minutes
plus a 5-minute re-walk.
