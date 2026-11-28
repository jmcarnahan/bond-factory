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
- Send the signed copy from the app's own mail path, then call `record_delivery`.
- Dependencies: Pillow 12.3+, reportlab 5.0+, pypdf 7.2+. An unsealed build is byte-identical only for the same versions of
  pypdf, reportlab and Pillow: do not rebuild a completed request after an upgrade.

## 4. What to test

- `make -C services/legacy_host test` (the provider over an existing envelopes table, two providers side by side, the tampered
  stored copy) and `make -C libs/bond_esign test`.
- In your app: a signed request becomes `completed` after one `fetch_signed_pdf`; a second call returns the same bytes; a
  tampered stored file is refused; an overdue open request reads `expired`; old vendor rows still answer through their provider.

## 5. Known limits

- Pages with a `/Rotate` other than 0 are skipped by the anchor search, and a stamp on one is refused.
- The web panel is for ONE signer at a time (each signer has their own link); the lib itself accepts up to ten signers.
- Typed names must be drawable with the standard PDF fonts (cp1252) unless the app passes a TTF through `Brand(font_path=)`
  and `Policy(typed_charset="any")`; otherwise the signer is asked to draw.
- The seal is optional and self-signed unless the app supplies a certificate; a self-signed seal shows "validity unknown".
- This is not legal advice: the app and its counsel own the consent text and any notices a contract needs.
