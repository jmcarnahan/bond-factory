# E-sign contract

Normative for `libs/bond_esign`: the evidence export (`bond.esign_evidence/0.1`), the hash rule behind its event
chain, and the form fields of the signing panel. Reasons: `docs/decisions/2026-11-27-native-esign.md`. How to use
the library: `libs/bond_esign/README.md`. Recorded sample: `fixtures/esign/evidence_0.1.json`, asserted by
`libs/bond_esign/tests/test_evidence_fixture.py`. The tables are pinned by `libs/bond_esign/tests/test_schema.py`.

This is a description of data, not legal advice.

## Evidence export

`bond_esign.evidence(session, t, request)` returns one JSON-serialisable dict. It reads only; it writes nothing.

```
{
  "schema":  "bond.esign_evidence/0.1",
  "request": { ... },
  "signers": [ { ... }, ... ],
  "events":  [ { ... }, ... ],
  "chain":   { "ok": bool, "count": int, "head": str | null },
  "check":   { "ok": bool, "problems": [str, ...] }
}
```

Every datetime is a string `YYYY-MM-DDTHH:MM:SSZ` (UTC, whole seconds) or `null`. Other values are plain JSON.

### `request`

Every column of the request table except `meta` (the app owns `meta`; the library never reads it).

| Key | Type | Meaning |
|---|---|---|
| `id` | string | request id (uuid4 text); part of every event hash |
| `status` | string | `open`, `signed`, `completed`, `declined`, `voided`, `expired` |
| `title` | string | document title as stored (control characters except tab and newline removed, cut at 500) |
| `subject_type`, `subject_id` | string or null | the app's own link |
| `document_sha256` | string | sha256 hex of the original PDF |
| `document_bytes`, `page_count` | int | size and pages of the original |
| `consent_version`, `consent_language` | string | what the signer agreed to |
| `consent_sha256` | string | sha256 hex of `consent_text` as UTF-8 |
| `consent_text` | string | the exact text the signer saw |
| `policy` | object | the `Policy` frozen at creation (every field of `Policy`) |
| `expires_at` | datetime or null | |
| `signed_sha256` | string or null | sha256 hex of the final PDF; set by `complete` |
| `sealed`, `timestamped` | bool | set by `complete` |
| `completed_at`, `voided_at`, `declined_at` | datetime or null | |
| `void_reason` | string or null | |
| `created_at`, `updated_at` | datetime | |
| `company_id` | string or null | only when the table is built from `TenantEsignRequestMixin` |

### `signers`

In `position` order. Every column of the signer table except `signature_png`, `token_sha256` and `code_sha256`
(the last two are credentials, not evidence), plus `signature_png_base64`.

| Key | Type | Meaning |
|---|---|---|
| `id`, `request_id`, `position` | string, string, int | `position` is 0-based and unique within the request |
| `name`, `email`, `role`, `key` | string or null (`email`, `key`) | as given at creation |
| `status` | string | `pending`, `signed`, `declined` |
| `placement`, `date_placement` | object or null | `{page, x, y, w, h}`; `page` is 1-based and already resolved; x, y, w, h are fractions of the page with the origin top-left |
| `token_expires_at` | datetime or null | when the link token stops working |
| `code_expires_at`, `code_sent_at`, `code_verified_at` | datetime or null | emailed one-time code |
| `code_attempts` | int | wrong codes since the last code was issued |
| `method` | string or null | `link`, `email_code`, `in_person`; set when signed |
| `witness` | string or null | the staff `actor` for an in-person signature |
| `signature_kind` | string or null | `typed` or `drawn` |
| `typed_name` | string or null | what the signer typed (also kept next to a drawn signature, when given) |
| `signature_sha256` | string or null | sha256 hex of the normalised PNG (drawn) or of the UTF-8 typed name (typed) |
| `signature_png_base64` | string or null | the normalised PNG, base64 (standard alphabet); null unless drawn |
| `signed_at` | datetime or null | |
| `ip`, `user_agent` | string or null | taken from the request context at signing |
| `decline_reason` | string or null | |
| `created_at`, `updated_at` | datetime | |

### `events`

In `seq` order, 1, 2, 3 and so on with no gaps. The request id is not repeated per event: take it from
`request.id`.

| Key | Type | Meaning |
|---|---|---|
| `seq` | int | position in the chain, starting at 1 |
| `signer_id` | string or null | the signer the event is about |
| `kind` | string | one of the kinds below |
| `at` | datetime | the `now` the app passed |
| `ip`, `user_agent`, `actor` | string or null | from the request context |
| `data` | object | kind-specific facts, below |
| `prev_hash` | string | the previous event's `row_hash`; 64 zeros for `seq` 1 |
| `row_hash` | string | sha256 hex over `prev_hash` and the canonical payload (next section) |

Event kinds and their `data`:

| Kind | `data` keys |
|---|---|
| `created` | `document_sha256`, `title`, `consent_version`, `consent_sha256`, `signers` (list of `{id, position, name, email, role, key}`), and `anchor_missing` (list of anchor texts not found) only when an anchor was not found |
| `token_issued` | `expires_at` (datetime string or null) |
| `viewed`, `code_sent`, `code_verified`, `expired`, `downloaded` | none (`{}`) |
| `code_failed` | `reason`: `wrong` or `expired` |
| `consent_given` | `version`, `language`, `sha256` (of the consent text) |
| `signed` | `kind`, `signature_sha256`, `method`, `typed_name`, `name` |
| `declined`, `voided` | `reason` |
| `document_built` | `sha256`, `pages`, `sealed`, `timestamped`, `timestamp_url` |
| `completed` | `sha256` |
| `copy_delivered` | `channel`, `reference` |

`data` holds only strings, ints, bools, null, lists and objects. A float is refused when the event is written.

### `chain` and `check`

- `chain.ok` is the result of `verify_chain`, `count` the number of events, `head` the last `row_hash` (null when
  there are no events).
- `check` is `verify_evidence`: the chain plus a cross-check of the request and signer rows against the facts the
  events recorded (names, emails, signature hashes, signed times, the final PDF hash). `problems` has one short
  sentence per mismatch. An empty list with `ok: true` means the rows agree with the events.

## The canonical hash

For each event the library builds this payload, in this form:

| Key | Value |
|---|---|
| `request_id` | `request.id` |
| `seq` | the event's `seq` |
| `signer_id` | string or null |
| `kind` | string |
| `at` | UTC, formatted `%Y-%m-%dT%H:%M:%SZ` (whole seconds, a trailing `Z`) |
| `ip`, `user_agent`, `actor` | string or null (as stored: control characters except tab and newline removed, `ip` cut at 64, `user_agent` at 1000, `actor` at 200) |
| `data` | the object, as stored |

Canonical bytes: `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8.
No spaces, keys sorted at every level, non-ASCII characters written as they are.

`row_hash = sha256(prev_hash_as_ascii + canonical_bytes)` as lowercase hex. `prev_hash` is 64 zeros for `seq` 1 and
the previous `row_hash` after that. The library exports these as `bond_esign.canonical(payload)` and
`bond_esign.row_hash(prev_hash, payload)`.

What the chain covers: changing, reordering or removing an event in the middle breaks every hash after it. What it
does not cover: removing the newest events leaves a valid shorter chain, and a party who can rewrite the whole log
can recompute every hash. Compare `chain.head` with the head printed on the signature certificate, and compare
`request.signed_sha256` with the hash of the stored final PDF.

## Verify a chain offline

Needs only the export. About a dozen lines of standard library Python:

```python
import hashlib, json

def verify(evidence):
    prev, request_id = "0" * 64, evidence["request"]["id"]
    for n, e in enumerate(evidence["events"], start=1):
        payload = {"request_id": request_id, "seq": e["seq"], "signer_id": e["signer_id"], "kind": e["kind"],
                   "at": e["at"], "ip": e["ip"], "user_agent": e["user_agent"], "actor": e["actor"], "data": e["data"]}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        want = hashlib.sha256(prev.encode("ascii") + body).hexdigest()
        if e["seq"] != n or e["prev_hash"] != prev or e["row_hash"] != want:
            return False, n  # the first event that does not check out
        prev = want
    return prev == evidence["chain"]["head"], len(evidence["events"])
```

`verify(json.load(open("fixtures/esign/evidence_0.1.json")))` returns `(True, 13)`.

## Form fields of the signing panel

`render_panel` writes a real `<form method="post">` marked `data-bond-esign`. `parse_submission(form,
max_signature_bytes=...)` reads the post. Names, as the browser sends them:

| Field | Element | Value |
|---|---|---|
| `consent_version` | hidden | the request's consent version; `sign()` refuses a different one (`consent_stale`) |
| `consent_accepted` | checkbox | `1` when ticked; absent when not. `1`, `on` and `true` (any case) read as accepted; anything else, or no field, reads as not accepted |
| `mode` | hidden | `typed` or `drawn`. The panel starts as `typed` when typed signatures are allowed, else `drawn`; the script changes it with the Draw and Type tabs |
| `typed_name` | text, max 120 characters | the signer's full name. Required in the markup when typed signatures are allowed. Trimmed; empty reads as none |
| `drawn_png` | hidden | empty, or a `data:` URL set by the script (below). Read only when `mode` is `drawn` |
| any name in `hidden=` | hidden | fields the app adds (a CSRF token); the library does not read them |

The `drawn_png` rule. The value must start with `data:image/png;base64,`. Anything else is refused with
`signature_invalid`. Before decoding, the base64 text must be no longer than `ceil(max_signature_bytes / 3) * 4 + 4`
characters; a longer value is refused with `signature_invalid` and is never decoded. Decoding is strict (standard
alphabet, no stray characters). The decoded bytes must begin with the PNG signature and be no longer than
`max_signature_bytes`; otherwise `signature_invalid`. The default cap is `Policy.max_signature_bytes`, 200,000 bytes.

`parse_submission` returns `Submission(consent_version, consent_accepted, typed_name, drawn_png)` and never raises
for a missing consent box, a blank name or a missing signature: `sign()` owns those rules (`consent_required`,
`signature_required`). The image is checked again, and cropped to its ink, by `sign()` (`normalise_png`: PNG only,
at most 2400 by 1200 pixels, at least 12 by 6 pixels of ink, and at least 60 ink pixels in all).

Without JavaScript the form still posts a typed signature: `mode` stays `typed` and `drawn_png` stays empty. When
only drawn signatures are allowed, a `<noscript>` notice says that JavaScript is needed.

## Changing this contract

The fixture test fails when a key is added, removed or renamed, or when the hash rule changes. Change the schema
string when a key is removed or renamed or a key changes meaning. Any change here updates
`fixtures/esign/evidence_0.1.json` and the library `CHANGELOG.md` in the same commit.
