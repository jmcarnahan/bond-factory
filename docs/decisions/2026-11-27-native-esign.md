# 2026-11-27 Native e-signing in the app's own page (bond_esign)

Status: accepted. Dated, append-only. Not legal advice: the legal points are a reading of public statutes and case
summaries. The adopting app and its counsel own the consent wording and any contract notices.

## Context

An adopter sends a customer an estimate PDF and the customer's signature is the acceptance. Today that runs through a
hosted signing vendor: the customer leaves the app, passes the vendor's consent and "adopt a signature" screens, and
comes back. A comparison of a hosted vendor, a young open-source app, three self-hosted signing apps
and two hosted APIs favoured a library inside the app.

- US ESIGN (15 USC 7006(5)) and the state UETAs define an electronic signature as any electronic sound, symbol or
  process adopted with intent to sign. A dispute turns on evidence of the process: who was sent the link, what they saw
  and agreed to, when and from where they signed, the exact document bytes, and a signed copy delivered at once. The
  law does not name a vendor.
- Self-hosted signing apps are a second web app with its own database, upgrades and advisories.

## Decisions

- **N1** Sign inside the app's own page. The customer ticks a consent box, types or draws a signature and taps one
  button: no third-party hop, no account, no vendor email.
- **N2** Nothing extra to operate. The product is a library inside the app's backend. It adds three tables and no
  service. (Libraries, not REST services: the standing rule for this repository.)
- **N3** The product of the library is the evidence trail: an append-only, hash-chained event log, the consent text
  and its hash, the original document's hash, and a signed PDF with a certificate page a layperson can read.
- **N4** Library only. The library takes bytes and returns bytes. Its service functions never read the clock (the caller passes
  `now`; only the certificate helper and the seal's signing time use the wall clock), and it never reads the environment or the
  client's address, never sends mail, stores no PDF and imports no sibling lib. The app owns the transaction, the
  clock, storage of both PDFs, mail and the client IP.
- **N5** Sealing is optional. Without a `Sealer`, integrity rests on the stored SHA-256 values, the chain head
  printed on the certificate and the app's own copies. A self-signed seal shows "validity unknown" in a PDF reader
  but still detects later change; a certificate from an authority readers trust is the app's choice and cost.
- **N6** Unsealed builds are byte-deterministic: the same request, events and original give the same bytes,
  so a retried job produces the same hash. Sealed output carries a time and is not.
- **N7** `sign()` is fast and `build_signed_pdf()` is a separate pure read run by the app's job worker, then
  `complete()`.
- **N8** The drawn signature image lives in the database, capped at 200,000 bytes. Typed signatures use the
  standard PDF fonts; other scripts need an app-supplied TTF.
- **N9** The chain is checked three ways: `verify_chain` (event rows), `verify_evidence` (request and signer rows
  against the events), and the printed head against the stored one. It cannot see removal of the newest events or a
  full rewrite by someone who controls the database; the printed head and `signed_sha256` cover that.

## Scope limits

Not for lender-mandated or regulated signing, identity proofing, notarisation or routing among many parties: those
stay with a vendor. An emailed one-time code can be required; it shows control of a mailbox, not identity. Multiple
signers and in-person signing are in the data model and the service functions; the web panel serves one signer at a
time.

## Dependencies and licences

All permissive, versions confirmed 2026-11-27: pypdf (BSD-3-Clause), reportlab (BSD), Pillow (MIT-CMU), SQLAlchemy
(MIT); extra `seal`: pyHanko (MIT) and cryptography (Apache-2.0 OR BSD-3-Clause); vendored in the browser panel:
signature_pad (MIT, licence kept in `NOTICE`). Excluded: PyMuPDF (AGPL), pikepdf (MPL), fpdf2 (LGPL), WeasyPrint as a
dependency (heavy system libraries; an app may use it to make its PDFs), and any GPL, AGPL or LGPL package.

## What stays with a vendor

Anything in the scope limits above, and any case where a counterparty requires a named vendor.

## Consequences

- An adopter owns consent wording, a named person who can explain the process, IP capture behind its proxy, a
  schedule for `expire_due`, and storage of both PDFs. The README lists them.
- `services/sdk_example` and `services/legacy_host` exercise the library (the second behind an existing envelope
  table and a five-method provider adapter), which satisfies P3 of `2026-11-12-adopter-proof.md`.
- Contract and fixture: `docs/contracts/esign.md`, `fixtures/esign/evidence_0.1.json`.
