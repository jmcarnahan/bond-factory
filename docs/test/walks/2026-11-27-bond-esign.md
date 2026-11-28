# bond_esign signing page walk (2026-11-27)

What was walked: the `services/sdk_example` signing page of `libs/bond_esign` (both build phases), commit 73a3955,
re-checks on the fix round after it, per `docs/test/WEB.md` "Web walk recipe: services/sdk_example signing page", by
one Sonnet walker (two lanes in turn) and the director's own re-check.
Stack: `sdk_example` on :8012 in fake mode, a throwaway SQLite database, zone America/Los_Angeles. Phone on web:
the same page at 390x844 (plain HTML, no Flutter). Simulator: not booted.
Shots pass: skipped: the build touched no Flutter screen.

## Web (1280x800)
| Step | User | Result | Note |
|---|---|---|---|
| 1 Open the link | signer link | PASS | title, PDF link, consent text in the page, panel; submit disabled |
| 2 Gates | signer link | PASS | consent alone keeps submit disabled; a typed name enables it |
| 3 Draw, Clear, draw again | signer link | PASS | |
| 5 Submit (typed) | signer link | PASS | 303 back, signed sentence, no form |
| 6 Job tick and download | signer link | PASS | 3 pages; typed name on the ruled line; certificate complete |
| Dialogs/popups on every page visited | | 0 | |

## Phone
| Step | Lane | User | Result | Note |
|---|---|---|---|---|
| 1 Open the link | phone-on-web 390x844 | signer link | PASS | no horizontal overflow; hit areas 44 px or more; keyboard order reaches every control; arrows switch tabs |
| 2 Gates | phone-on-web | signer link | PASS | |
| 3 Draw, Clear, draw again | phone-on-web | signer link | PASS | page scrolls outside the canvas |
| 4 Rotate and resize | phone-on-web | signer link | PASS | strokes kept and crisp after 844x390, 1280x800 and back |
| 5 Submit (drawn) | phone-on-web | signer link | PASS | 303 back, signed sentence, no form |
| 6 Job tick and download | phone-on-web | signer link | PASS | 3 pages; signature beside "Accepted by (customer)"; certificate has name, UTC and local time, IP, hashes, timeline |
| 7 Replay | phone-on-web | signer link | PASS | still one `signed` event |
| 8 Expired and voided pages | phone-on-web | signer link | PASS | one sentence, no form |
| 9 No JavaScript | phone-on-web (JS-disabled context) | signer link | PASS | typed signature signs; tabs and canvas hidden |
| 10 Evidence | curl as demo-user-1 | demo-user-1 | PASS | `chain.ok`, `check.ok`; kinds in the recipe's order |
| X1 Forced submit of an empty drawing | phone-on-web | signer link | FAIL, then PASS on re-walk | see P1 |
| X2 Back after signing | phone-on-web | signer link | PASS | signed state, no stale form |
| Console / runtime errors, popups | | | clean after the fix round, 0 | first pass: a favicon 404 on every load (P6) |

Previous walk's open items: none: first walk of this page.

Defects (all found on the first pass; the screenshots were deleted at cleanup):
- P1 (minor): Draw mode, canvas cleared, submit forced: the blank canvas was posted and the page said "could not be
  read" instead of "signature required". Fixed (the script posts a drawing only when the pad has ink); re-walked PASS.
- P2 (copy): a voided request read "This document is not ready to sign yet." Fixed: "This document can no longer be
  signed."; re-checked.
- P3 (minor, left as is): expired and voided pages of the demo still link the original PDF. An app decides this.
- P4 (minor): in the demo's own sample PDF the caption printed on the ruled line. Fixed in the sample (line 2.5pt
  under the label baseline, as a WeasyPrint row has it); the re-rendered page was looked at.
- P5 (minor): certificate footer "Page 1 of 1" on page 3 of the file. Fixed: "Certificate page n of m".
- P6 (minor): favicon 404 in the console. Fixed (empty icon link).
- P7 (minor): canvas backing store 340 px for a 338 px content box. Fixed (content box); re-walked 338/338. The
  headless browser has devicePixelRatio 1, so sharpness at 2x and 3x was not exercised: hand test on a phone.
- Found on the re-walk: the demo serves the panel assets with a one-hour cache, so the browser ran the old script
  after the fix. `asset_tags` now adds `?v=<content hash>` to each URL; re-walked with the new URLs.

Timing: about 6 minutes for both lanes; the re-walk two calls.

## Re-walk after the readiness fix round (2026-11-27, working tree on top of 6630da4)

Only what the round changed on the page: recipe step 11 (Decline) at 390x844 and 1280x800, plus one typed sign,
job tick and download as a regression check. Driven by the director with Playwright (headless), fresh demo database.

| Step | Lane | Result | Note |
|---|---|---|---|
| 11 Decline | 390x844 | PASS | "Decline to sign" link 44px tall under the sign button; closed until pressed; reason field and outlined "Decline" button; 303 back; "You declined to sign this document. Nothing was signed."; same after reload; no form left; no overflow |
| 11 Decline | 1280x800 | PASS | same |
| Evidence of the declined request | | PASS | `created`, `token_issued`, `viewed`, `declined` with the reason; chain and check ok |
| 5-6 Sign (typed), tick, download | 390x844 | PASS | signed page shows no decline control; certificate reads "Signed via Private signing link"; evidence ends `downloaded` with `{"document": "signed"}` |
| Console errors, CSP violations, dialogs | | clean, 0 | |

Not re-walked: steps 1-4 and 7-10 (unchanged by the round); the decline form with JavaScript disabled (it has no script; covered by the service tests).
