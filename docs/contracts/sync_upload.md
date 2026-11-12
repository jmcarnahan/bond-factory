# Sync upload contract

Normative for `bond_sync` (Dart client) and `bond_sync_py` (Python server). Fixtures for every shape below are in
`fixtures/sync/`; both implementations test against them. Route paths are the app's choice (the example uses
`/sync/upload`, `/sync/token`, `/sync/jwks.json`).

## Upload request: `POST /sync/upload`

The caller is the signed-in session user, never a field of the body. Unknown fields are refused (422).

```json
{"transaction_id": 8, "ops": [
  {"seq": 0, "op": "put", "table": "notes", "id": "note-1", "data": {"title": "First note"}}]}
```

| Field | Rule |
|---|---|
| `transaction_id` | int or null |
| `ops` | at most 100; `seq` values unique (a duplicate or 101 ops is a 422) |
| `op.seq` | int, 0 or more; ops are applied in `seq` order |
| `op.op` | `put`, `patch` or `delete` |
| `op.table` | 1 to 64 chars |
| `op.id` | at most 256 chars on the wire; the dispatcher accepts only `[A-Za-z0-9_-]{1,64}` (whole string) |
| `op.action` | optional, 1 to 32 chars; Dart omits it when null |
| `op.data` | object; a put carries every non-null column, a patch only the changed ones |

A bad id is one `invalid` verdict, never a 422. Fixtures: `upload_request_ok.json`,
`upload_request_mixed.json`, `upload_request_too_many_ops.json`, `upload_request_dup_seq.json`, `bad_ids.json`.

## Upload response

Always 200 with one result per op, even when every op was refused. A refused op never stops the next.

```json
{"results": [{"seq": 0, "status": "ok"},
             {"seq": 1, "status": "rejected", "code": "invalid", "message": "title_required"},
             {"seq": 2, "status": "skipped", "code": "already"}],
 "server_now": "2026-11-08T17:04:05.123Z"}
```

- `status`: `ok`, `rejected` or `skipped`. `code`, `message` and `resolved_id` are omitted when unset.
- `resolved_id` (on `ok`): the server row that replaces the id the device chose.
- `server_now`: ISO 8601 UTC with milliseconds and `Z`. It is the server's clock at the end of the batch. A host may
  inject a clock (`upload(..., now=callable)`), and `server_now` then follows it, so a walk can pin the server time and
  a phone's server clock follows the pin.

Fixtures: `upload_response_mixed.json` (the exact answer to the mixed request, see below),
`upload_response_all_codes.json` (one example per verdict, for client parsers).

## Verdict codes

| Code | Status | Meaning |
|---|---|---|
| `invalid` | rejected | bad id, bad value shape, NUL byte, or a handler refusal |
| `unsupported` | rejected | no route for table/action/op (`Not supported`), or a `rest_only` table (`Use the REST route`) |
| `conflict` | rejected | the id collides with another row; a put that finds its own row already written is `ok` |
| `not_found` | rejected | the row does not exist |
| `forbidden` | rejected | the row is not the caller's |
| `rate_limited` | rejected | too many writes |
| `server_error` | rejected | an unmapped failure in one op |
| `already` | skipped | the op needed no work |

Default `message` texts. These are normative for what the shared core produces; a handler may set its own text.

| Code | Produced by | Default `message` |
|---|---|---|
| `invalid` | id fails the pattern | `That id is not valid` |
| `invalid` | NUL byte in id or data | `That value is not valid` |
| `invalid` | wrong value shape (coercion, data error) | `invalid` (the code) |
| `unsupported` | no route for table/action/op | `Not supported` |
| `unsupported` | `rest_only` table | `Use the REST route` |
| `conflict` | integrity error on a put or patch | `conflict` (the code) |
| `server_error` | unmapped failure | `server_error` (the code) |
| `already` | skipped | no `message` |
| `not_found`, `forbidden`, `rate_limited` | handler or `reject_for` | the app's text (examples: `Not found`, `That is not your row`) |

A rejected result always carries a `message`; when none is given it equals the code.

Apps may add codes (for example a phone-format refusal); clients show `message` for a code they do not know.
A database that is unavailable (connection, pool timeout, SQLSTATE class 08, 40, 53 or 57 except 57014, or no
SQLSTATE) is NOT a verdict: the route answers HTTP 503 `db_unavailable` with `Retry-After: 5` and the client retries the whole batch.

## Mixed fixture preconditions

`upload_request_mixed.json` against the example app, signed in as any user: the table `notes` has one row,
`note-taken`, owned by another user. Expected: seq 0 and 1 `ok`; 2 `invalid` (bad id); 3 `skipped already`
(delete of a missing row); 4 `conflict`; 5 `invalid` message `title_required`; 6 `not_found`; 7 `unsupported`.

## Sync token: `POST /sync/token`

```json
{"token": "<jwt>", "expires_at": "2026-11-08T17:15:00Z", "endpoint": "http://localhost:8095",
 "server_now": "2026-11-08T17:04:05.123Z"}
```

- `expires_at`: ISO 8601 UTC, seconds, `Z`. `endpoint` is the sync service URL.
- Sync not configured: `503 {"detail": {"code": "sync_off", "message": "..."}}`.
- JWT: ES256 only (EC P-256), header `{alg: ES256, kid, typ: JWT}`, claims `{sub: user id, aud, iat: int, exp: int}`.
  Defaults: audience `powersync`, 15 minutes (clamped to 1 to 60), kid `bond-sync-1`.
- The token only lets a device read its slice; writes use the ordinary session on `/sync/upload`.

## JWKS: `GET /sync/jwks.json`

```json
{"keys": [{"kty": "EC", "crv": "P-256", "x": "...", "y": "...", "kid": "bond-sync-1", "alg": "ES256", "use": "sig"}]}
```

Public, `Cache-Control: public, max-age=300`, 404 when sync is not configured. While a key is being rotated the
set holds the current key and the previous one (it needs its own `kid`), so tokens already minted still verify.

Fixtures: `jwks_example.json` and `sync_token_claims.json` (header, claims, an example token signed by the test key,
the token response and the `sync_off` body). The key is a throwaway test key.
