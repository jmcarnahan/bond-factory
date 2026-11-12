# bond_api

HTTP `ApiClient`, typed exceptions and error hooks over `package:http`. Pure Dart: no Flutter, no `dart:io`.

## Public API

| Name | What it does |
| --- | --- |
| `ApiClient` | base URL, `http.Client`, optional `TokenSource`, timeouts, session hooks |
| `getJson` `postJson` `putJson` `patchJson` `deleteJson` | `Map<String, Object?>` in and out (empty body reads `{}`) |
| `getJsonList` `getBytes` `requestBytes` `postMultipart` `sse` | arrays, raw bytes (`requestBytes` takes any method and a JSON body), uploads, event streams |
| `timeout:` and `headerTimeout:` on `request`, the JSON helpers, `getBytes`, `requestBytes`, `openStream` | per-call limits; null uses the client's value. `timeout` is the overall limit of a call. For a JSON or bytes call it covers the wait for the headers and the whole body read. `headerTimeout` is only the wait for the response headers, and it is never longer than `timeout`. For `openStream` (and `sse`) both bound the wait for the headers, and `timeout` also bounds reading an error body; once a 2xx answer has started, neither limits the stream (the SSE idle timeout does). Null for either uses the client's value. |
| `ApiException` family | `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `BadRequest`, `ValidationError`, `ServerError`, `BadResponse`, `NetworkError`, `NetworkFailure(kind)` |
| `ErrorBody.parse(status, body)` | maps string, dict and list `detail` forms to the right exception |
| `networkFailureText(ApiException e, ApiLabels labels, {String baseUrl = ''}) -> String` | one sentence for a failed request |
| `TokenSource`, `SessionRefresh` | session seam; `renewed`, `rejected`, `offline` |
| `SseEvent`, `SseFrameSplitter`, `parseSseFrame` | the event-stream parser |
| `authPathsExcludedFromRenewal` | `/auth/firebase`, `/auth/refresh`, `/auth/demo` |

## 401 and 403 behaviour

- A 401 to an authenticated request calls `onUnauthorized` once (concurrent 401s share the call).
- `renewed` replays the request exactly once with the new token.
- `rejected` throws `Unauthorized(refreshRejected: true)`; `offline` throws `NetworkFailure(noAnswer)` and keeps the session.
- When the session is over, `onSessionRevoked` (code `session_revoked`) and then `onSessionExpired` run once.
- A 403 `deactivated` runs `onDeactivated` once. The auth paths never renew and fire no hooks.
- `endsSession: (ErrorBody) => bool` (optional) is asked on every 401 of a signed-in call (not an auth path), before and after a renewal. When it returns false there is no renewal and no hook: the call throws `Unauthorized` with the code kept. A callback that throws is logged and counts as true. Null means every 401 ends the session.
- On a 401 or 403 with a string `detail`, a top-level `code` or `error_code` is the code; the detail text is the code only when neither exists.

## Depend on it

```yaml
dependencies:
  bond_api:
    git:
      url: https://github.com/jmcarnahan/bond-factory.git
      ref: <full 40-char sha>
      path: packages/bond_api
```

Pin the full SHA; tags are labels only. Sibling `bond_json` resolves through the same repo.

## Example

```dart
final api = ApiClient(
  baseUrl: Uri.parse('https://api.example.test/api/v1'),
  http: http.Client(),
  tokens: myTokenStore, // implements TokenSource
  onUnauthorized: () async => (await auth.refresh()) ? SessionRefresh.renewed : SessionRefresh.rejected,
  onSessionExpired: () async => auth.signOut(),
);
try {
  final me = await api.getJson('/auth/me');
} on ApiException catch (e) {
  print(networkFailureText(e, const ApiLabels(), baseUrl: api.baseUrl.toString()));
}
```

## Test

```
make -C packages/bond_api test
```

Tests use `package:http/testing.dart` `MockClient`; `bond_test_support` is Flutter and not used here.
