# 2026-11-12 Download grant delivery and hooks

Status: accepted. Dated, append-only.

## Context

The grant router (`bond_storage.make_download_router`) could only stream a file through the service, and an app could
not record who downloaded what or set its own columns on a grant. An app whose links redirect to a short-lived signed
URL, and keep an audit row per download, could not adopt it without losing behaviour.

## Decisions

- **G1** `delivery="stream"` stays the default. `delivery="redirect"` (with `presign_seconds`, default 60) answers 302
  to a signed URL when the backend can presign. It checks that the object exists, claims the download, then redirects.
  A backend with no presigned URLs (the local one) streams as before, so one router serves both.
- **G2** `on_claim(session, grant, ip)` runs in the same transaction as the claim: both commit together. If it raises,
  both roll back and the request fails (500). It replaces `after_download` in redirect mode: the bytes never pass
  through the service, so the two together raise `ValueError`.
- **G3** `mint(..., extra=)` merges a mapping into the grant row so an app's own columns can be set. A name that is
  one of the library's columns raises `ValueError` (`grants.LIB_COLUMNS` lists them).
- **G4** Small switches, each defaulting to today: `resolve(..., enforce_cap=True)`, `gone_body` (a string or a
  callable that takes the request and must not vary by failure reason), `enabled()` (checked per request, before the
  rate limit; false answers a JSON 404) and `client_ip(request)`.
- **G5** In redirect mode a missing object is 410 and the claim is not spent. The URL is signed before the claim, so a
  signing fault is 503 and spends nothing; the retry works.

## Consequences

- The stream path still loads the whole object into memory: no backend offers a chunked read yet.
- A deployment on a presigning backend gets the redirect by passing one argument. The example keeps its stream call
  and has one test that mounts redirect mode over the local backend and sees the stream fallback.
