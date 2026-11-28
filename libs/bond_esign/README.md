# bond_esign

Sign a PDF on your own web page. The signer ticks a consent box, types or draws a signature and taps one button.
The library records who was sent the link, what they saw and agreed to, when and from where they signed and the
exact document bytes, in an append-only, hash-chained log. It then builds a signed PDF: the original pages with
the signature stamped in place, plus a "Signature certificate" page. A cryptographic seal is optional.

A library only: SQLAlchemy 2.0 table mixins, service functions, a PDF builder and an inline web panel. No router,
no FastAPI, no environment reads, no mail, no file storage. Contract: `docs/contracts/esign.md`. Reasons:
`docs/decisions/2026-11-27-native-esign.md`.

**This is not legal advice.** The default consent text is a starting point. The adopting app and its counsel own
the wording and any notices a contract needs.

## What it is not for

Use a signing vendor, not this library, for lender-mandated or regulated signing, identity proofing, notarisation
and routing among many parties. The library records an emailed one-time code as a way to verify a signer (off by
default); it does not check who a person is.

## Install

```
pip install "bond_esign @ git+https://github.com/jmcarnahan/bond-factory.git@<full-sha>#subdirectory=libs/bond_esign"
pip install "bond_esign[seal] @ git+https://github.com/jmcarnahan/bond-factory.git@<full-sha>#subdirectory=libs/bond_esign"
```

Poetry form: `docs/sdk/README.md`, "Python". Python 3.12 or 3.13.

| Package | Needed for | Licence |
|---|---|---|
| `sqlalchemy>=2.0.36` | tables and queries | MIT |
| `pypdf>=7.2,<8` | read, merge, find printed text | BSD-3-Clause |
| `reportlab>=5.0,<6` | stamp and certificate pages | BSD |
| `pillow>=12.3` | check and crop the drawn signature | MIT-CMU |
| `pyhanko>=0.38.2,<0.39` (extra `seal`) | PAdES seal, timestamp | MIT |
| `cryptography>=48.0` (extra `seal`) | self-signed certificate helper | Apache-2.0 OR BSD-3-Clause |
| `signature_pad` 5.1.8, vendored in `bond_esign/web/` | drawing on a canvas | MIT |

An unsealed build is byte-identical for the same inputs and the same versions of pypdf, reportlab and Pillow: do not
rebuild a completed request after a dependency upgrade (keep and serve the stored copy).

`import bond_esign` needs no `seal` extra: the seal names (`Sealer`, `verify_seal`, `make_self_signed_pkcs12`) load on
first use and raise an ImportError that names the extra. Without the extra, `hasattr(bond_esign, "Sealer")` raises
ImportError, not AttributeError.

## The flow

Every service function is `f(session, t, ..., now=...)`. `t` is `Tables(request, signer, event)`. `now` is a naive UTC
datetime from your clock. The service functions never read the clock (the caller passes `now`); only the certificate
helper `certs.py` and pyHanko's seal time use the wall clock. Every function flushes and none commits.

| Step | Call |
|---|---|
| 1. Open a request for the PDF | `create_request(session, t, pdf=, title=, signers=[SignerSpec], consent=, now=, ...)` |
| 2. Make the signer's link | `issue_token(session, t, signer, now=)` returns the raw token once; only its hash is stored (or skip it: see `find_signer_by_key` below) |
| 3. Signer opens the link | `find_signer_by_token(session, t, token, now=)` or `find_signer_by_key(session, t, request_id, key)`, then `signing_view(session, t, signer, ctx=, now=)` and `render_panel(view, action_url=)` |
| 4. Signer posts the form | `parse_submission(form, max_signature_bytes=)`, then `sign(session, t, signer, pdf=, ...)` |
| 5. Job: build | `build_signed_pdf(session, t, request, pdf=original)` is a pure read; safe to retry |
| 6. Job: keep and record | store both PDFs, then `complete(session, t, request, signed=)` |
| 7. Send the copy | the app mails it, then `record_delivery(session, t, request, channel=, reference=, now=)` |
| Later | `record_download`, `evidence`, `verify_chain`, `verify_evidence`, `verify_seal` |
| Other endings | `decline(session, t, signer, reason=, ctx=, now=)`, `void(session, t, request, reason=, ctx=, now=)`, `expire_due(session, t, now=)` |
| With the emailed code | `issue_code(session, t, signer, now=)` returns the 6 digits (you email them); `verify_code(session, t, signer, code, ctx=, now=)` |

An app that already has its own page credential can skip `issue_token`/`find_signer_by_token` and use
`find_signer_by_key(session, t, request_id, key)`: it returns the signer of that request whose `key` is the app's own
reference (the lowest position when several share it), or None. It writes nothing.

Full keyword lists (all after `session, t`; `*` marks the end of positional arguments):

- `create_request(session, t, *, pdf, title, signers, consent, now, policy=Policy(), subject_type=None, subject_id=None,
  expires_at=None, company_id=None, meta=None, ctx=None)`
- `sign(session, t, signer, *, pdf, consent_version, consent_accepted, typed_name, drawn_png, ctx, now, method="link")`
- `record_download(session, t, request, *, signer=None, ctx=None, now)`
- `record_delivery(session, t, request, *, channel, reference=None, signer=None, ctx=None, now)`

`create_request` takes the PDF (at most `Policy.max_pdf_bytes`, 25,000,000 by default; encrypted PDFs are
`invalid_pdf`), 1 to `Policy.max_signers` signers (10 by default), and `expires_at`, `subject_type`/`subject_id` (your
link to an estimate, order or similar), `company_id` (only on a table built from `TenantEsignRequestMixin`) and `meta`
(yours; never read). Bad inputs (blank title, name or consent, a past `expires_at`, a policy that allows no
signature mode) raise `ValueError`, not `EsignError`. `sign()` is fast: the page can say thanks at once and the PDF
follows from the job.

`sign()` checks, in order: a signer who already signed is a replay (`SignOutcome.replay` is True, nothing is written,
even if the payload differs); the request is open and not expired; the PDF's sha256 equals the one stored at
creation (`document_mismatch`); consent was ticked and its version is current; the emailed code was verified when
the policy or `method="email_code"` asks for it; an in-person signature has `ctx.actor`; a signature is present and
allowed. It then writes `consent_given` and `signed` events. When every signer has signed, the request becomes
`signed`.

## The three tables

The mixins own the table names, foreign keys and constraints. Datetimes are naive UTC. `tests/test_schema.py` pins
every column.

Types are SQLAlchemy generic types: they become `DATETIME`/`BLOB` on SQLite and `TIMESTAMP WITHOUT TIME ZONE`/`BYTEA`
on PostgreSQL (checked with `CreateTable` for both). `str` columns are `VARCHAR`; `sha256` columns are `VARCHAR(64)`;
long text is `TEXT`; "JSON" is the generic `JSON`. Columns are NOT NULL unless marked `null`.

| Table | Columns (type; `null` = nullable) |
|---|---|
| `esign_requests` | `id` str; `status` str; `title` str; `subject_type`, `subject_id` str null; `document_sha256` sha; `document_bytes`, `page_count` int; `consent_version`, `consent_language` str; `consent_sha256` sha; `consent_text` text; `policy` JSON; `expires_at` datetime null; `signed_sha256` sha null; `sealed`, `timestamped` bool; `completed_at`, `voided_at`, `declined_at` datetime null; `void_reason` text null; `meta` JSON; `created_at`, `updated_at` datetime null; `company_id` str with the tenant mixin |
| `esign_signers` | `id` str; `request_id` str; `position` int; `name` str; `email` str null; `role` str; `key` str null; `status` str; `placement`, `date_placement` JSON null; `token_sha256` sha null; `token_expires_at` datetime null; `code_sha256` sha null; `code_expires_at`, `code_sent_at`, `code_verified_at` datetime null; `code_attempts` int; `method`, `witness`, `signature_kind`, `typed_name` str null; `signature_png` LargeBinary null; `signature_sha256` sha null; `signed_at` datetime null; `ip` str null; `user_agent`, `decline_reason` text null; `created_at`, `updated_at` datetime null |
| `esign_events` | `id` str; `request_id` str; `seq` int; `signer_id` str null; `kind` str; `at` datetime; `ip` str null; `user_agent` text null; `actor` str null; `data` JSON; `prev_hash`, `row_hash` sha |

Defaults are SQLAlchemy column defaults, not database `DEFAULT` clauses, so a migration needs none: `id` is a uuid4
string; `sealed` and `timestamped` are false; `meta` is `{}`; `code_attempts` is 0; `data` is `{}`. `created_at` and
`updated_at` default to `func.now()` (`updated_at` also on update); the service sets both explicitly from your `now`,
so the stored values are your clock's. `status` has no column default: the service sets `open` and `pending`.

```python
import bond_esign as es
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase): ...
class EsignRequest(es.EsignRequestMixin, Base): ...      # or es.TenantEsignRequestMixin
class EsignSigner(es.EsignSignerMixin, Base): ...
class EsignEvent(es.EsignEventMixin, Base): ...
T = es.Tables(request=EsignRequest, signer=EsignSigner, event=EsignEvent)
```

**Migration.** The library ships none: write your own to match. Constraints and indexes the mixins declare:
`esign_requests` primary key `id` and index `ix_esign_requests_subject` on `(subject_type, subject_id)` (plus
`ix_esign_requests_company_id` with the tenant mixin); `esign_signers` primary key `id`, foreign key `request_id` to
`esign_requests.id` ON DELETE CASCADE with an index on it, unique `uq_esign_signers_request_position` on
`(request_id, position)`, unique `token_sha256`; `esign_events` primary key `id`, foreign key `request_id` to
`esign_requests.id` ON DELETE CASCADE, unique `uq_esign_events_request_seq` on `(request_id, seq)`. `esign_events`
has no separate `request_id` index: that unique's leading column serves. The unique on `token_sha256` is unnamed
(the table's own `UNIQUE (token_sha256)`). The signature
image is a `LargeBinary` column, at most `Policy.max_signature_bytes` (200,000) after cropping.

## Statuses, events, errors

Request status: `open`; `signed` (every signer signed); `completed` (`complete` stored the final PDF); `declined`
(any signer declined); `voided`; `expired`. `void` is refused once every signer has signed, built or not (status `signed` or `completed`: `already_completed`, "This
document has already been signed."); open (also partly signed), declined and expired requests can be voided; on a voided
request it changes nothing. `expire_due` turns open requests past `expires_at` into `expired`; `signing_view`, `sign`
and `issue_token` do the same for the request they touch. Signer status: `pending`, `signed`, `declined`. Signing
`method`: `link`, `email_code`, `in_person`.

Event kinds (constants and `KINDS`): `created`, `token_issued`, `viewed` (at most one per signer per
`Policy.view_event_gap_seconds`, 3600), `code_sent`, `code_verified`, `code_failed`, `consent_given`, `signed`,
`declined`, `voided`, `expired`, `document_built`, `completed`, `copy_delivered`, `downloaded`. Their `data` keys are
in the contract. `data` takes only strings, ints, bools, null, lists and dicts; a float raises `TypeError`.

`EsignError(code, message)`: `message` is plain English fit to show a signer. Codes are in `bond_esign.errors.CODES`.

| Code | Raised when |
|---|---|
| `not_open` | the request or signer is not open (signed, declined, voided) |
| `expired` | past `expires_at` or already expired |
| `already_completed` | `void` on a request every signer has signed (`signed` or `completed`) |
| `consent_required` / `consent_stale` | box not ticked / the consent version posted is not the request's |
| `code_required` | the policy needs the emailed code and it is not verified |
| `code_invalid` | `verify_code` with no code waiting |
| `code_too_soon` / `too_many_attempts` | a new code inside `code_resend_seconds` (30) / `code_max_attempts` (5) wrong codes |
| `signature_required` | neither a typed name nor a drawing |
| `signature_invalid` | the drawing is not a usable PNG (type, size, empty, too small, bad data URL) |
| `typed_not_allowed` / `drawn_not_allowed` | the mode is off in the policy |
| `name_not_renderable` | the typed name has characters the standard fonts cannot draw |
| `in_person_needs_actor` | `method="in_person"` without `ctx.actor` |
| `document_mismatch` | the PDF given differs from the one the request was made for |
| `invalid_pdf` | unreadable, encrypted, no pages, or over `max_pdf_bytes` |
| `too_many_signers` | more than `Policy.max_signers` |
| `not_ready` | build or `complete` before every signer signed |
| `hash_conflict` | `complete` again with a different final PDF |
| `seal_failed` | the seal certificate or timestamp step failed |
| `evidence_mismatch` | `build_signed_pdf` found rows that disagree with the hashed events |

## The hash chain

Each event's `row_hash` is `sha256(prev_hash + canonical JSON)` of `{request_id, seq, signer_id, kind, at, ip,
user_agent, actor, data}`. Canonical JSON: sorted keys, separators `,` and `:`, `ensure_ascii=False`, UTF-8. `at` is
`YYYY-MM-DDTHH:MM:SSZ`. `prev_hash` for `seq` 1 is 64 zeros. Exact rule and an offline check:
`docs/contracts/esign.md`. `append` locks the request row (`FOR UPDATE`; a no-op on SQLite) before it reads `seq`,
and nothing in the library updates or deletes an event row.

`verify_chain` finds the first broken `seq`. `verify_evidence` also checks the request and signer rows against the
facts the events recorded, so an edited name or signature shows up; `build_signed_pdf` refuses a failing record.
Neither detects removal of the newest events, or a rewrite of the whole log: compare the chain head printed on the
certificate and `request.signed_sha256`.

## Where the signature goes

```python
box = es.Placement(page=-1, x=0.55, y=0.80, w=0.30, h=0.0615)  # page 1-based, -1 = last; fractions, origin top-left
rule = es.AnchorRule("Accepted by (customer)")                  # find printed text instead
spec = es.SignerSpec("Pat Example", "pat@example.com", anchor=rule, date_placement=None)
```

A `placement` wins over an `anchor`; with neither, the signer appears on the certificate only. An anchor is resolved
once, at `create_request`. If the text is not found the signer has no placement and the `created` event lists the
text under `anchor_missing`. `AnchorRule` fields: `occurrence` (0-based over all pages in reading order; -1 last),
`dx`, `dy` (box origin from the text's right edge and baseline), `w`, `h`, `case_sensitive`. Limits in v1: pages with a
`/Rotate` other than 0 are skipped, and the right edge of the text is estimated with Helvetica widths at the run's
font size, not the font the PDF embeds. A stamp on a rotated page raises `ValueError`. Fractions are of the page's
CropBox, else its MediaBox. `fixtures/esign/weasy_acceptance.pdf` is a document laid out the way a WeasyPrint estimate
is; the defaults put the box on the ruled line beside the label. `weasy_acceptance_tight.pdf` is the same page with the default line height (its line is about 2.3 pt below the label
baseline); `weasy_acceptance.pdf` has `line-height: 1.4` (about 4 to 5 pt). The caption band sits in the bottom 8 pt of
the box, and with the `AnchorRule` defaults (`dy=-0.045`, `h=0.0615`) the box bottom is 13 pt below the label baseline on
a Letter page, so the caption starts about 7.8 pt below it: a ruled line 2 to 6 pt below the label baseline stays clear
of the caption, and the signature area ends 5 pt below the baseline, on the line.

The stamp: a drawn image is scaled to fit and anchored bottom-left; a typed name is set in Times-Italic and shrunk to
fit. A caption ("Signed electronically by <name>, <date>, ref <first 8 of the signer id>") takes an 8 pt band at the
bottom of the box. A `date_placement` adds the date as text.

## Typed or drawn

`Policy(allow_typed=True, allow_drawn=True)`; at least one must be on. A drawn signature is a PNG from the panel,
checked by `normalise_png`: PNG only, at most 2400 by 1200 pixels and `max_signature_bytes`, at least 12 by 6 pixels
and 60 pixels of ink, then cropped to the ink and re-encoded without metadata. The signer's typed name (at most 120
characters) is kept next to a drawing when given. A typed name must be drawable with the standard PDF fonts
(`Policy.typed_charset="latin-1"`, the default; English and Spanish pass). For other scripts set
`typed_charset="any"` and pass `Brand(font_path="<a TTF>")` to `build_signed_pdf`. Otherwise `name_not_renderable`
tells the signer to draw. `typed_renderable(name, charset)` lets you check first.

```python
policy = es.Policy(require_email_code=True, typed_charset="any")
signed = es.build_signed_pdf(session, T, request, pdf=original, labels=es.CertificateLabels.spanish(),
                             brand=es.Brand(name="Example Co", accent_rgb=(31, 79, 216)), zone="America/Los_Angeles")
```

`Brand` (certificate and stamp only): `name`, `logo_png`, `accent_rgb`, `font_path`. `zone` is an IANA name for the
local time column on the certificate (UTC stays). The certificate holds the title and request id, the original
document's SHA-256 and page count, one block per signer (name, email, role, how verified, witness, times, IP, device,
consent version and hash, signature), the event timeline, the consent text and a "how to verify" line with the chain
head.

## What the app must do

- **Store both PDFs.** The original, because `sign` and `build_signed_pdf` take its bytes and check their hash; and the
  signed one from `build_signed_pdf`, before you call `complete`. The library stores neither.
- **Skip a completed request in the job, and serve only a signed copy that matches.** The job does nothing for a
  request that is already `completed` and never overwrites a stored signed copy (a rebuild under a changed zone or a
  seal would differ from the recorded hash). Serve the signed copy only when its sha256 equals
  `request.signed_sha256`; otherwise answer 404.
- **Send the signed copy and record it.** The library never sends mail. Email the final PDF, then call
  `record_delivery`.
- **Pass a real client IP.** Fill `RequestContext(ip=, user_agent=)` from the request. Behind a proxy or load balancer
  use your framework's trusted-proxy setting; an audit row holding the proxy's address is worthless. The library
  stores what you pass (at most 64 characters).
- **Run `expire_due` on a schedule** (a job tick is enough), so old requests close and get their `expired` event.
- **Own the consent wording.** `default_consent(company_name=, paper_contact=, language="en"|"es")` returns version
  `bond-esign-consent/1`. Write your own `Consent(version, language, text)` and change the version when the words change.
- **Keep a named person** who can explain the process (links, consent, the evidence) if a signature is questioned.
- **Serve the web assets** (below) and **add CSRF** through `hidden={"csrf": ...}` in `render_panel`. The library
  does not read hidden fields you add.
- **Own the transaction.** Commit after `create_request` (and `issue_token`) before the signer can act: a rollback
  after a refused `sign` would otherwise discard the uncommitted request. Commit after a successful call. An `EsignError` leaves nothing to keep, so roll back;
  the one exception is `expired`, where the flip to `expired` survives only if you commit (`expire_due` also sweeps it).
- **Run the build in a job worker**, not in the request. Sealing uses pyHanko's synchronous API: call it from sync code.

## The web panel

`render_panel(view, *, action_url, labels=PanelLabels(), hidden=None, error=None, id_prefix="bond-esign")` returns an
HTML fragment, escaped, no template engine: a `<form method="post">` with the consent text in the page, the consent
checkbox, "Your full name", Draw and Type tabs (only the allowed modes), a canvas with Clear, an error line and the
submit button. When signing is not possible it returns one sentence instead (signed, expired, not ready, needs a
code). Form fields: `docs/contracts/esign.md`.

Serve the files from `asset_names()` (`bond-esign.css`, `bond-esign.js`, `signature_pad.umd.min.js`,
`LICENSE-signature_pad`) from the paths `asset_path(name)` gives, and put `asset_tags("/your/static")` in the page head. Each URL from `asset_tags` ends in
`?v=<content hash>`, so the files can be cached for a long time and a library upgrade is never served stale.

- No dialog, popover or overlay anywhere. No inline script, style or event handler, so a strict Content-Security-Policy
  works (allow your own origin for script and style).
- Without JavaScript the form still posts a typed signature; the tabs and canvas stay hidden and a `<noscript>` hint
  says so. A drawn-only policy needs JavaScript.
- With JavaScript the submit button stays disabled until the consent box is ticked and there is a typed name (Type) or
  ink (Draw). Strokes redraw after a resize or rotation; touch targets are at least 44 px; `touch-action: none` is on
  the canvas only.
- **Theme** by overriding five custom properties in a rule for `.bond-esign` that comes after the library stylesheet
  (they are declared on `.bond-esign`, so setting them on `:root` has no effect): `--bond-esign-accent`,
  `--bond-esign-border`, `--bond-esign-text`, `--bond-esign-surface`, `--bond-esign-radius`.
- **Labels.** `PanelLabels()` and `CertificateLabels()` hold every visible string in English; `.spanish()` gives
  Spanish. Pass your own for another language. The default consent text exists in English and Spanish.

## Sealing (optional)

Off unless you pass a `Sealer` to `build_signed_pdf`. Install the `seal` extra.

```python
p12 = es.make_self_signed_pkcs12("Example Co Seal", "Example Co", years=5, passphrase=b"change-me")  # or load yours
sealer = es.Sealer.from_pkcs12(p12, b"change-me", timestamp_urls=("https://tsa.example.com",), require_timestamp=False)
signed = es.build_signed_pdf(session, T, request, pdf=original, sealer=sealer)
check = es.verify_seal(signed.pdf, expected_fingerprint=sealer.fingerprint)   # present, intact, covers_whole_file, trusted
```

A PAdES signature over the whole file, with one invisible signature field. Timestamp servers are tried in order; if
all fail the file is sealed without a timestamp, unless `require_timestamp=True`, which raises `seal_failed` (so does
`require_timestamp` with no server). `intact` means unchanged since sealing, not who sealed it: store
`sealer.fingerprint` and pass it back as `expected_fingerprint`; `trusted` is then True or False (None when none was
given). `SealCheck.signed_at` is the seal's own time (the timestamp server's when it was timestamped, else the
signing clock pyHanko read), not the `now` you passed. A self-signed seal shows "validity unknown" in Acrobat, but a change after sealing is still detected. A seal
from a certificate authority your readers trust is the way to a green tick.

Make a throwaway certificate: `python -m bond_esign.certs --cn "Example Co Seal" --org "Example Co" --out seal.p12`
(prompts for the passphrase; writes the file with mode 600; prints the base64 for a secret store). Never commit it.

Unsealed builds are byte-deterministic: the build uses the events before `document_built`, so a retried job gets
the same bytes and hash. An app must still never rebuild or overwrite a completed request's stored copy: an event
appended between the first build and `complete` (a new token, say) changes a later rebuild. Sealed output is not (the signature carries a
time), so seal once and store that file; `complete` then refuses a different one (`hash_conflict`).

## A minimal wiring

About 50 lines, FastAPI-free, shown as plain functions. Run against SQLite in memory. Replace `store` and
`send_copy` with your storage and mail.

```python
from datetime import UTC, datetime, timedelta

import bond_esign as es
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase): ...
class EsignRequest(es.EsignRequestMixin, Base): ...
class EsignSigner(es.EsignSignerMixin, Base): ...
class EsignEvent(es.EsignEventMixin, Base): ...
T = es.Tables(request=EsignRequest, signer=EsignSigner, event=EsignEvent)

def now():  # the app owns the clock: naive UTC
    return datetime.now(UTC).replace(tzinfo=None)

def start(session, pdf: bytes, name: str, email: str) -> str:
    """Create the request and return the raw link token (show or email it once)."""
    request = es.create_request(
        session, T, pdf=pdf, title="Estimate 1042", now=now(),
        signers=[es.SignerSpec(name, email, anchor=es.AnchorRule("Accepted by (customer)"))],
        consent=es.default_consent(company_name="Example Roofing", paper_contact="help@example.com"),
        expires_at=now() + timedelta(days=14))
    signer = session.scalars(select(T.signer).where(T.signer.request_id == request.id)).one()
    return es.issue_token(session, T, signer, now=now())

def page(session, token: str, ip: str, agent: str, error: str | None = None) -> str | None:
    signer = es.find_signer_by_token(session, T, token, now=now())
    if signer is None:
        return None  # answer 404
    view = es.signing_view(session, T, signer, ctx=es.RequestContext(ip, agent), now=now())
    return es.asset_tags("/esign/static") + es.render_panel(
        view, action_url=f"/esign/sign/{token}", hidden={"csrf": "<your token>"}, error=error)

def submit(session, token: str, form: dict, original_pdf: bytes, ip: str, agent: str):
    signer = es.find_signer_by_token(session, T, token, now=now())
    if signer is None:
        return None  # answer 404
    request = session.get(T.request, signer.request_id)
    try:
        sub = es.parse_submission(form, max_signature_bytes=es.policy_of(request).max_signature_bytes)
        out = es.sign(session, T, signer, pdf=original_pdf, consent_version=sub.consent_version,
                      consent_accepted=sub.consent_accepted, typed_name=sub.typed_name,
                      drawn_png=sub.drawn_png, ctx=es.RequestContext(ip, agent), now=now())
    except es.EsignError as exc:
        session.rollback()  # nothing to keep (commit instead on "expired" to keep the flip)
        return page(session, token, ip, agent, error=exc.message)
    session.commit()
    return out  # all_signed -> enqueue job(); replay=True -> nothing was written

def job(session, request_id: str, original_pdf: bytes, store, send_copy):
    request = session.get(T.request, request_id)
    signed = es.build_signed_pdf(session, T, request, pdf=original_pdf)  # pure read, safe to retry
    store(request.id, signed)                                            # keep BOTH PDFs first
    es.complete(session, T, request, signed=signed, now=now())
    reference = send_copy(request, signed.pdf)                           # the app sends the mail
    es.record_delivery(session, T, request, channel="email", reference=reference, now=now())
    session.commit()
```

`services/sdk_example` wires the same calls into FastAPI routes and a `bond_jobs` handler; `services/legacy_host`
puts them behind an existing envelope table with a five-method provider adapter.

## Checking later

```python
es.verify_chain(session, T, request)      # ChainCheck(ok, count, broken_seq)
es.verify_evidence(session, T, request)   # EvidenceCheck(ok, chain, problems)
es.evidence(session, T, request)          # the export in docs/contracts/esign.md, with "check"
es.sha256_hex(stored_signed_pdf) == request.signed_sha256
```

## Tests

`make -C libs/bond_esign test T=tests/test_x.py`; `make -C libs/bond_esign lint`. SQLite in memory, no network.
Tests marked `postgres` (row locks) run with `make pg-up && make test-pg`, then `make pg-down`.
