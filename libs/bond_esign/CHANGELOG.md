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
- Service: `create_request`, `issue_token`, `find_signer_by_token`, `signing_view`, `issue_code`, `verify_code`, `sign`, `decline`,
  `void`, `expire_due`, `build_signed_pdf`, `complete`, `record_delivery`, `record_download`, `evidence`, `policy_of`, `verify_evidence` (returns `EvidenceCheck(ok, chain, problems)`:
  the hash chain plus every signer and request row checked against the hashed events; `build_signed_pdf` refuses a failing
  record with `evidence_mismatch`). `complete` raises `ValueError` when `signed.sha256` or `signed.pages` do not match its bytes.
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
