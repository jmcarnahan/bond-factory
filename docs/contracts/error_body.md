# Error body contract

Normative for `bond_api` (Dart client) and `bond_service_kit` (Python server). Every error response carries
one shape:

```json
{"detail": {"code": "not_found", "message": "Thing not found", "hint": "optional"}}
```

- `code`: lowercase snake case, stable, for programs. `message`: for people. `hint`: optional extra.
- Other fields (`errors`, `data`) may ride along; clients ignore what they do not know.

## Normalising what a handler raised

| Raised detail | Becomes |
|---|---|
| dict | fields kept; missing `code` and `message` are added |
| string matching `^[a-z][a-z0-9_]*$` | `code` = the string, `message` = underscores to spaces |
| any other string | `message` = the string, `code` from the status table |

## Status to default code

| Status | Code | Status | Code |
|---|---|---|---|
| 400 | `bad_request` | 413 | `too_large` |
| 401 | `unauthorized` | 415 | `unsupported_media_type` |
| 403 | `forbidden` | 422 | `invalid` |
| 404 | `not_found` | 429 | `rate_limited` |
| 405 | `method_not_allowed` | 501 | `not_implemented` |
| 409 | `conflict` | 502 | `bad_gateway` |
| 500 | `internal_error` | 503 | `unavailable` |

A database outage on 503 uses `db_unavailable` instead of `unavailable`.

## Validation errors

Status 422:

```json
{"detail": {"code": "validation_error", "message": "<loc>: <msg>",
            "errors": [{"loc": ["body", "field"], "msg": "...", "type": "..."}]}}
```

The server never echoes the rejected input.

## Retry-After

- 429 sends `Retry-After: 60`.
- 503 `db_unavailable` sends `Retry-After: 5`.
- Clients honour the header when present and otherwise use their own backoff.

## Legacy string form

Older servers send `{"detail": "string"}`. `bond_api` parses it: the string is the message, and the code when
the status is 401 or 403. `bond_service_kit` emits the object form; a compatibility flag
(`legacy_detail_string`) leaves a string detail untouched for apps that still need it.

## Client parsing (`bond_api`)

The parser accepts `detail` as a string, a map (`message` falling back to `detail`, plus `code` and `data`) or
a list of field errors, and falls back to a top-level `code`. Typed errors: `Unauthorized`, `Forbidden`,
`NotFound`, `Conflict`, `BadRequest`, `ValidationError`, `ServerError`, `BadResponse`, `NetworkFailure`.
