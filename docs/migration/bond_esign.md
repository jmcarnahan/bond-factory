# Migrating to bond_esign

Native e-signing (`libs/bond_esign`: SQLAlchemy, pypdf, reportlab, pillow; the `seal` extra adds pyHanko). The signer ticks a
consent box, types or draws a name and taps one button on the app's own page. The lib keeps a hash-chained evidence log
and builds the signed PDF with a certificate page. A library only: no router, no mail, no file storage.
Contract: `docs/contracts/esign.md`. Reasons: `docs/decisions/2026-11-27-native-esign.md`. Legend: `docs/migration/README.md`.
Not for lender-mandated or regulated signing, identity proofing or routing among many parties: keep a vendor for those.

## 1. What it replaces

An app that sends a PDF to a signing vendor: the envelope call, the hosted signing page, the status poll and the download of
the completed file. The app keeps its own envelopes table and its provider seam; the lib sits behind that seam as one more
provider, so old vendor rows keep working and nothing is migrated.

## 2. What the app adds

The model is `services/legacy_host/legacy_host/esign_native.py` (about 100 lines, the whole adapter): copy it and rename.

- Three tables from the mixins (`EsignRequestMixin`, `EsignSignerMixin`, `EsignEventMixin`) and your own migration; the lib
  ships none (`libs/bond_esign/README.md`, "The three tables"). Write your own column on the request (the host adds
  `legacy_estimate_id`) to join to the app's record.
- Five provider methods over the lib: `create_envelope` (`create_request` with an `AnchorRule` on the printed label, then store
  the original PDF), `recipient_view_url` (`issue_token`, then the link to the app's page), `void`, `status`, `fetch_signed_pdf`.
- The signing page and post: `find_signer_by_token`, `signing_view`, `render_panel`, `parse_submission`, `sign`
  (`services/sdk_example/sdk_example/routes/esign_pages.py` is the reference), the static assets from `asset_names()`, a strict CSP.
- Storage for both PDFs, mail for the signed copy, the client IP, the consent wording, and the transaction (commit after
  `create_request` and `issue_token`, roll back after a refused `sign`).

Status mapping used by the host (the lib's `open` has no "viewed" state, so the host reads the `viewed` event):

| Lib request status | Host word |
|---|---|
| `open`, no `viewed` event | `sent` |
| `open`, a `viewed` event | `delivered` |
| `signed` | `completed` (everyone has signed; the signed PDF can be fetched: `fetch_signed_pdf` builds, stores and completes it) |
| `completed`, `declined`, `voided`, `expired` | the same word |

The app's old code treats "completed" as "every signer has signed and the signed PDF can be fetched", so `signed` maps to it.

## 3. Behaviour to know

- `sign()` is fast and only records. The signed PDF exists after `build_signed_pdf` and `complete`. In the host,
  `fetch_signed_pdf` does both when the request is `signed` and then stores the result, so a poller that wants the file calls
  it when `status` is `completed`. An app with a job worker runs the same two calls there instead
  and has `fetch_signed_pdf` only read the stored copy.
- `fetch_signed_pdf` compares the stored copy's sha256 with `request.signed_sha256` and refuses a mismatch
  (`SIGNED_COPY_MISMATCH`, not retryable). Never rebuild or overwrite a completed request's stored copy.
- The host has no scheduler, so its `status` runs `expire_due` first. An app with a worker runs `expire_due` on its tick.
- `fetch_signed_pdf` on a request that is not yet fully signed raises a retryable error; on a declined, voided or expired one a
  non-retryable error.

## 3a. How an existing app's code calls the seam

Rehearsed in `services/legacy_host` (`esign_seam.py`, `tests/test_esign_adopter_calls.py`). Adapt the adapter to these habits:

- Completion: the app's job asks `status()` and raises (to retry later) unless it says "completed", then calls
  `fetch_signed_pdf`. Map lib `signed` to "completed"; fetch builds, stores and completes.
- Take-back: the app calls `void`, and when that raises its cannot-void code it asks `status()` and answers "already signed"
  only when the state is "completed". `void` now refuses once every signer has signed (`already_completed`, also for a
  built-not-yet-completed `signed` request): map it to the app's cannot-void code, so a take-back in the seconds before the
  build job cannot destroy a given acceptance.
- No webhook with native signing: the app's own sign POST commits and enqueues the same completion job the webhook used to
  enqueue, then redirects (303) to the page with the marker the page already understands (`event=signing_complete`). Until the
  job has run, that page says the signature is being recorded and shows no form.
- The label beside the signature line: read it from the same per-document setting the old vendor adapter used (default
  "Accepted by (customer)") for the `AnchorRule`.
- The default anchor box (`AnchorRule`, `dy=-0.045`, `h=0.0615`) puts its bottom 13 pt below the label's baseline on a Letter
  page, so it suits a ruled line 2 to 6 pt below the label baseline (a WeasyPrint table-cell border, with or without
  `line-height: 1.4`). Render your own document once and look at a stamped copy; tune `dy`/`h` if the line sits elsewhere.
- The document's validity date goes in as `expires_at` when it is in the future.
- An app whose page already has its own credential finds the signer with `find_signer_by_key(session, t, request_id, key)`
  and skips `issue_token`.
- The client IP is the signature's evidence: check the proxy setting that makes it real (for uvicorn,
  `--forwarded-allow-ips`), or every signer appears to sign from the proxy.
- Send the signed copy from the app's own mail path, then call `record_delivery`. It is refused (`not_ready`) until the request is `completed` (the signed copy exists only then): the certificate prints "Signed copy delivered".
- Dependencies: Pillow 12.3+, reportlab 5.0+, pypdf 7.2+. An unsealed build is byte-identical only for the same versions of
  pypdf, reportlab and Pillow: do not rebuild a completed request after an upgrade.

## 4. What to test

- `make -C services/legacy_host test` (the provider over an existing envelopes table, two providers side by side, the tampered
  stored copy) and `make -C libs/bond_esign test`.
- In your app: a signed request becomes `completed` after one `fetch_signed_pdf`; a second call returns the same bytes; a
  tampered stored file is refused; an overdue open request reads `expired`; old vendor rows still answer through their provider.

## 4a. What the adopter still has to build

A dry-run integration into an adopter found these gaps. Each is app work, not library work. Tick them off before launch.

- [ ] A signed-copy route on the public page. It serves the stored signed PDF only after comparing its sha256 with `request.signed_sha256`, and calls `record_download` (why: the log should show who fetched it, and a changed file must never be served).
- [ ] Email the signed copy to the signer, then `record_delivery` (why: the consent text promises a copy, and the outside signing vendor's completion email no longer exists).
- [ ] `record_download(document="original")` where the public page serves the original PDF (why: the log shows what the signer was able to read).
- [ ] `record_sent` when the link is emailed or texted, and again with `reminder=True` on every resend (why: the certificate timeline then shows when the signer was reached).
- [ ] `sign(..., method="app_link")` when the signer arrives through the app's own share link instead of a token from `issue_token` (why: the certificate says "Private link issued by the sender", which is true; the library does not verify who the signer is with link methods, the app's link is the credential).
- [ ] `signing_view(..., record_view=False)` for HEAD requests and link-preview fetches (why: a mail scanner or chat preview is not the signer viewing).
- [ ] Page state after signing: show "signed, your copy is being prepared" from the library's signer status, and offer the signed copy once the request is `completed`. A reload must never offer signing again. Render from the view's `can_sign`, not from the app's own older status column (why: the old column lags the job).
- [ ] Map `expired`, `not_open` and `document_mismatch` to plain messages for a superseded or taken-back document (why: the signer should not see a code).
- [ ] The decline control: pass `decline_url` to `render_panel`, read the reason with `parse_decline`, call `decline`, then do what the app does on decline (status, staff notice) (why: a signer needs a way to say no).
- [ ] Language per signer: Spanish consent text, `PanelLabels.spanish()` and `CertificateLabels.spanish()`, chosen from the signer's language and not the staff user's (why: the signer must read what they agree to).
- [ ] Brand colour: override `--bond-esign-accent` and the other four panel properties in a rule for `.bond-esign` that comes after the library stylesheet (`libs/bond_esign/bond_esign/web/README.md`).
- [ ] The consent text needs the business name and a non-blank paper-contact line. Take both from the app's settings and pass them to `default_consent`; the provider seam passes only a session (why: a blank contact line makes the paper alternative empty).
- [ ] Privacy and terms pages that name the outside vendor: change them, in both languages (why: they would be wrong after cutover).
- [ ] Register the new provider name in config validation and startup checks. Keep the vendor's webhook route for old envelopes (why: old envelopes still complete through it).
- [ ] The migration for the three tables, plus every "list of all tables" guard the app has: demo-data purge classification, sync or export allowlists, schema-drift pins (why: a missed list silently skips or deletes evidence). Import the three mapped classes where the metadata is assembled.
- [ ] An asset route for the panel files with long immutable caching (the URLs carry a content hash), and a rate limit keyed by IP, not by link. If the app forbids blocking work in async routes, run the sign POST's PDF work in a threadpool (why: the link is the credential, and PDF work blocks).
- [ ] Dependencies: the library brings pypdf and reportlab. Re-lock. The Pillow floor is 12.3.
- [ ] The date blank: `SignerSpec.date_anchor`. Printed text extraction usually merges a table row into one run, so a short label such as "Date" cannot be found by itself: anchor on the signature label with a larger `dx`. For the default acceptance block (fixture `fixtures/esign/weasy_acceptance.pdf`) the measured rule is `AnchorRule("Accepted by (customer)", dx=0.505, dy=-0.014, w=0.12, h=0.02)`; the test `test_date_anchor_lands_in_the_date_blank_on_the_signature_row` pins it. Re-measure if the template's columns change.
- [ ] No demo shortcut: tests complete a request by posting the panel form (why: a shortcut hides a broken page).
- [ ] One open request per subject is the app's rule: void the old request before creating a new one (the library does not stop a second).
- [ ] Time: pass naive UTC for every `now` and `expires_at`; a "valid until" date becomes the end of that day in the business's zone, converted to UTC (`libs/bond_esign/README.md`, "Time").
- [ ] Before launch: one hand test on a real phone; open a sealed file in Acrobat if sealing is switched on; legal review of the consent text.

## 5. Known limits

- Pages with a `/Rotate` other than 0 are skipped by the anchor search, and a stamp on one is refused.
- The web panel is for ONE signer at a time (each signer has their own link); the lib itself accepts up to ten signers.
- Typed names must be drawable with the standard PDF fonts (cp1252) unless the app passes a TTF through `Brand(font_path=)`
  and `Policy(typed_charset="any")`; otherwise the signer is asked to draw.
- The seal is optional and self-signed unless the app supplies a certificate; a self-signed seal shows "validity unknown".
- This is not legal advice: the app and its counsel own the consent text and any notices a contract needs.
