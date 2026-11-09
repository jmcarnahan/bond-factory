# bond_api

HTTP `ApiClient`, typed exceptions and error hooks over `package:http`. Pure Dart: no Flutter, no `dart:io`.

## Public API

| Name | What it does |
| --- | --- |
| `ApiClient` | base URL, `http.Client`, optional `TokenSource`, timeouts, session hooks |
| `getJson` `postJson` `putJson` `patchJson` `deleteJson` | `Map<String, Object?>` in and out (empty body reads `{}`) |
| `getJsonList` `getBytes` `postMultipart` `sse` | arrays, raw bytes, uploads, event streams |
| `ApiException` family | `Unauthorized`, `Forbidden`, `NotFound`, `Conflict`, `BadRequest`, `ValidationError`, `ServerError`, `BadResponse`, `NetworkError`, `NetworkFailure(kind)` |
| `ErrorBody.parse(status, body)` | maps string, dict and list `detail` forms to the right exception |
| `networkFailureText(e, ApiLabels)` | one sentence for a failed request |
| `TokenSource`, `SessionRefresh` | session seam; `renewed`, `rejected`, `offline` |
| `SseEvent`, `SseFrameSplitter`, `parseSseFrame` | the event-stream parser |
| `authPathsExcludedFromRenewal` | `/auth/firebase`, `/auth/refresh`, `/auth/demo` |

## 401 and 403 behaviour

- A 401 to an authenticated request calls `onUnauthorized` once (concurrent 401s share the call).
- `renewed` replays the request exactly once with the new token.
- `rejected` throws `Unauthorized(refreshRejected: true)`; `offline` throws `NetworkFailure(noAnswer)` and keeps the session.
- When the session is over, `onSessionRevoked` (code `session_revoked`) and then `onSessionExpired` run once.
- A 403 `deactivated` runs `onDeactivated` once. The auth paths never renew and fire no hooks.

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
