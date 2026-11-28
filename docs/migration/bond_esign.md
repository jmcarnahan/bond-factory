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
| `signed` | `delivered` (everyone has signed; the signed PDF is not built yet) |
| `completed`, `declined`, `voided`, `expired` | the same word |

## 3. Behaviour to know

- `sign()` is fast and only records. The signed PDF exists after `build_signed_pdf` and `complete`. In the host,
  `fetch_signed_pdf` does both when the request is `signed` and then stores the result, so a poller that wants the file must call
  it when `status` is `delivered` and every signer has signed. An app with a job worker runs the same two calls there instead
  and has `fetch_signed_pdf` only read the stored copy.
- `fetch_signed_pdf` compares the stored copy's sha256 with `request.signed_sha256` and refuses a mismatch
  (`SIGNED_COPY_MISMATCH`, not retryable). Never rebuild or overwrite a completed request's stored copy.
- The host has no scheduler, so its `status` runs `expire_due` first. An app with a worker runs `expire_due` on its tick.
- `fetch_signed_pdf` on a request that is not yet fully signed raises a retryable error; on a declined, voided or expired one a
  non-retryable error.

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
