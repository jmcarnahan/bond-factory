# Changelog

## 0.1.0 - unreleased
First release: sign a PDF on the app's own page, with an append-only evidence log.

- Tables (mixins): `EsignRequestMixin`, `TenantEsignRequestMixin` (adds nullable indexed `company_id`), `EsignSignerMixin`,
  `EsignEventMixin` for `esign_requests`, `esign_signers`, `esign_events`; `Tables(request, signer, event)`.
- Types: `Placement`, `AnchorRule`, `SignerSpec`, `RequestContext`, `Consent`, `Policy` (incl. `typed_charset`), `Brand`, `Stamp`,
  `SigningView`, `SignOutcome`, `SignedDocument`, `ChainCheck`, `SealResult`, `SealCheck`, `CertificateData`, `CertificateSigner`,
  `CertificateEvent`, `CertificateLabels`.
- Errors: `EsignError(code, message)` and the `errors` module (22 codes incl. `evidence_mismatch`, `errors.CODES`).
- Events: kind constants `CREATED`, `TOKEN_ISSUED`, `VIEWED`, `CODE_SENT`, `CODE_VERIFIED`, `CODE_FAILED`, `CONSENT_GIVEN`, `SIGNED`,
  `DECLINED`, `VOIDED`, `EXPIRED`, `DOCUMENT_BUILT`, `COMPLETED`, `COPY_DELIVERED`, `DOWNLOADED`, `KINDS`; `append`, `chain`,
  `verify_chain`, `row_hash`, `canonical`; module `events`. Event `data` rejects floats (TypeError).
- Service: `create_request`, `issue_token`, `find_signer_by_token`, `find_signer_by_key(session, t, request_id, key)` (the signer whose `key` is the app's reference, lowest position first, or None), `signing_view`, `issue_code`, `verify_code`, `sign`, `decline`,
  `void` (refused with `already_completed` once every signer has signed, i.e. status `signed` or `completed`), `expire_due`, `build_signed_pdf`, `complete`, `record_delivery`, `record_download`, `evidence`, `policy_of`, `verify_evidence` (returns `EvidenceCheck(ok, chain, problems)`:
  the hash chain plus every signer and request row checked against the hashed events; `build_signed_pdf` refuses a failing
  record with `evidence_mismatch`). `complete` raises `ValueError` when `signed.sha256` or `signed.pages` do not match its bytes.
- `AnchorRule.h` defaults to 0.0615 (was 0.055): the box bottom is 13 pt below the label baseline on Letter, so the stamp caption clears a ruled line 2 to 6 pt below it (a real estimate with `line-height: 1.4` had it struck through).
- Readiness round (A-I). (A) events `LINK_SENT`, `REMINDER_SENT` and `record_sent(session, t, request, *, channel, reference=None, signer=None, reminder=False, ctx=None, now)` (open requests only, else `expired` / `not_open`; an overdue request is flipped to `expired`, so commit); `record_delivery` is refused with `not_ready` until the request is `completed`; `record_download(..., document="signed" | "original")` (signed needs a completed request; the event data carries `document` and the certificate timeline prints "Signed copy downloaded" or "Original document downloaded"; `CertificateEvent.detail`, `CertificateLabels.event_label(kind, detail)`). The three `record_*` functions raise `ValueError` when `signer` does not belong to the request. (B) method `app_link`; the certificate heading "Verified by" is now "Signed via" (es "Firmado mediante"), because it claimed a verification the library cannot vouch for. (C) `signing_view(..., record_view=False)` writes no `viewed` event. (D) `SignerSpec.date_anchor`, resolved at `create_request` into `date_placement` (which wins); a text not found is listed in `anchor_missing`. The date box must be on the same page as the signature box: a date anchor on another page, or with no signature box, is dropped and listed in `anchor_missing`; an explicit `date_placement` on another page is a `ValueError`. (E) the stamp caption cuts the signer name to 40 characters (never ending on a combining mark or a space) plus "..."; with `Brand.font_path`, caption and certificate names that cp1252 cannot draw use that font instead of "?" (`_text.font_for`). (F) `find_signer_by_key` cleans the key like `create_request` does. (G) panel decline control: `render_panel(..., decline_url=)`, `parse_decline`, the four new `PanelLabels` fields `decline_summary`, `decline_reason_label`, `decline_submit`, `declined_message`; a declined signer's closed panel now shows `declined_message`; `PanelLabels` moved to `webform_labels.py` and is still importable from `webform` and the barrel. (H) documentation only (README and contract). (I) the certificate timeline and chain head use the events up to and including the last `signed` event (was: before the first `document_built`), so events recorded between the last signature and `complete` cannot change a rebuild; the printed sentence reads "the head hash after the last signature".
- Dependency floors: `reportlab>=5.0,<6`, `pillow>=12.3`.
- Signature and consent: `normalise_png`, `typed_renderable`, `default_consent` (en, es; version `bond-esign-consent/1`).
- PDF facts and documents: `sha256_hex`, `page_count`, `find_anchor`, `stamp`, `certificate_pages`.
- Web panel: `render_panel`, `parse_submission`, `PanelLabels`, `Submission`, `asset_path`, `asset_names`, `asset_tags`.
- Seal (extra `seal`): `Sealer` (with `.fingerprint`), `verify_seal(pdf, expected_fingerprint=None)` (`SealCheck.fingerprint`, `.trusted`;
  `intact` means unmodified, not who sealed it), `make_self_signed_pkcs12`. Names from `anchor`, `stamp`, `certificate`, `webform`,
  `seal` and `certs` load on first use, so `import bond_esign` works without the extra.
- `evidence` exports every request column except `meta`, every signer column except `signature_png`, `token_sha256` and
  `code_sha256` (plus `signature_png_base64`), the events in seq order, `chain {ok, count, head}` and `check {ok, problems}`.
- Fixes before release: `/Rotate` given as an indirect object is read through pypdf's `page.rotation`; the panel script posts a drawing only
  when the pad has ink (an empty Draw pad gives `signature_required`) and sizes the canvas from its content box; the closed-panel sentence
  for a request that is not open reads "This document can no longer be signed."; the certificate footer reads "Certificate page n of m".
- `asset_tags(base_url)` URLs carry `?v=<content hash>` so a cached asset is never stale after an upgrade.
