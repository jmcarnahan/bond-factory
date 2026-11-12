# Changelog

## 0.1.0 - unreleased
- Scaffold.
- `ErrorBody` reads the error code from `code`, then `error_code`, then `error` (detail map first, then top level). Only non-empty strings count (an empty `code` does not beat `error_code`); `error` counts only when it matches `^[a-z][a-z0-9_]*$` (at most 64 chars) and never overwrites `message`.
- `ApiClient`: bearer token from a `TokenSource`, `getJson/postJson/putJson/patchJson/deleteJson` (maps), `getJsonList`, `postMultipart`, `getBytes`, `sse`. Header, overall and upload timeouts; timeouts and connection failures throw `NetworkFailure`; an unparsable 2xx body throws `BadResponse`.
- 401 handling: `onUnauthorized` renews the session once (concurrent 401s share one call); `renewed` replays the request exactly once, `rejected` throws `Unauthorized(refreshRejected: true)`, `offline` throws `NetworkFailure(noAnswer)`. `onSessionRevoked` (code `session_revoked`) then `onSessionExpired` run once when the session is over. 403 `deactivated` runs `onDeactivated` once. All hooks are settable after construction. `authPathsExcludedFromRenewal` (`/auth/firebase`, `/auth/refresh`, `/auth/demo`) never renew and never fire hooks.
- Exceptions: the superset of the consuming apps' families. `Unauthorized(message, code, refreshRejected)`, `Forbidden(message, code, hint)`, `NotFound(message, code, data)`, `Conflict`, `BadRequest(message, code)`, `ValidationError(message, fields, code, data)`, `ServerError(message, statusCode, code)`, `BadResponse`, `NetworkError`, `NetworkFailure`. `data` is `Map<String, Object?>`.
- `ErrorBody.parse(status, body)`: dict, string and list `detail`, a top-level `code`, validation `errors`, raw JSON text or non-JSON text.
- `networkFailureText(e, ApiLabels, {baseUrl})` with const English `ApiLabels`; `asNetworkFailure`; `userDetail`.
- `SseEvent`, `SseFrameSplitter`, `parseSseFrame`: multi-line `data:`, `event:`, `id:`, `retry:`, comments, CRLF and lone CR, chunks split anywhere.
- `TokenSource` (bond_auth's token store implements it), `StaticTokenSource`, `SessionRefresh` (bond_auth and bond_sync re-export it rather than redefine it).
- Dependencies added: `http_parser` (multipart content types).
- Decision: the 401 hook names follow the phase 1 brief (`onUnauthorized` renews). The seed client called the renewal hook `onSessionExpired` and the sign-out hook `onUnauthorized`; here `onSessionExpired` is the sign-out signal.
- Not lifted from the seed client: the web socket helper, the explicit-bearer request mode, the push-token path exemption, `installGlobalErrorHooks` (Flutter), the localized strings (replaced by `ApiLabels`), `debugPrint` (replaced by `log`), `kIsWeb` (replaced by `isWeb`).
