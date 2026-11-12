# Migrating to bond_api

`ApiClient`, the typed `ApiException` family, `ErrorBody.parse`, SSE and `networkFailureText`
(`packages/bond_api`, pure Dart). Needs `bond_json` through the same SHA. Legend: `docs/migration/README.md`.

Contracts: `docs/contracts/error_body.md`.

## 1. What it replaces

Paths are relative to `flutterui/packages/<core>/lib/src/` (A `avalon_core`, P `pt_core`): `api/` for the client files, `providers/` for the wiring.

| App | Goes away | Shrinks or stays |
|---|---|---|
| A | `api_client.dart` 509, `api_exception.dart` 173, `sse.dart` 32 | `network_failure_text.dart` 20 becomes an adapter; `error_hooks.dart` 25 stays (Flutter); `avalon_api.dart` 2,206 keeps its 218 `_client.<verb>(` calls |
| P | `api_client.dart` 367, `api_exception.dart` 148 | `network_failure_text.dart` 20 adapter; `error_hooks.dart` 25 and `device_anchor.dart` 18 stay; `paga_api.dart` 1,565 keeps 123 verb calls |
| S | phone `mobile/crm_proposals/lib/core/api/{api_client 178, api_exception 76}.dart`, `SseFrameSplitter` in `lib/data/calendar_assistant/stream.dart:14` | web has no client (51 files in `flutterui/lib` import `package:http`): later |

## 2. The adapter

Verb shim, so the 218 + 123 call sites keep returning `Object?` (bond has `request(method, path, ...)`):

```dart
extension AppVerbs on ApiClient {
  Future<Object?> get(String path, {Map<String, Object?>? query}) => request('GET', path, query: query);
  Future<Object?> post(String path, {Object? body, Map<String, Object?>? query}) =>
      request('POST', path, body: body, query: query);
  Future<Object?> put(String path, {Object? body}) => request('PUT', path, body: body);
  Future<Object?> patch(String path, {Object? body}) => request('PATCH', path, body: body);
  Future<Object?> delete(String path) => request('DELETE', path);
}
```

Client wiring (A `providers/core_providers.dart:35`, P `:30`). Set the 30 s total the seed used; bond defaults to 60 s:

```dart
final apiClientProvider = Provider<ApiClient>((ref) => ApiClient(
      baseUrl: Uri.parse(ref.watch(apiBaseUrlProvider)),
      http: ref.watch(httpClientProvider),
      tokens: ref.watch(tokenStoreProvider), // the app's TokenStore implements bond_api TokenSource
      timeout: const Duration(seconds: 30),
    ));
```

Hooks: the two names swap. A `providers/auth_provider.dart:788-793` and P `:498-502` become:

```dart
client.onUnauthorized = ref.read(firebaseEnabledProvider) ? controller.refreshSession : null; // was onSessionExpired
client.onSessionExpired = controller.sessionExpired; // was onUnauthorized: the session is over
client.onDeactivated = controller.accountDeactivated;
client.onSessionRevoked = () async => controller.markRevoked(); // A only
```

`networkFailureText` adapter (import bond_api with `hide networkFailureText`, or name this adapter differently, else the two collide; A keeps its `AvL10n` strings; bond's returns a sentence always, A's returned null):

```dart
String? networkFailureText(AvL10n l, Object error, {required String baseUrl}) {
  final f = asNetworkFailure(error, baseUrl: baseUrl);
  if (f == null) return null;
  final url = f.baseUrl.isEmpty ? baseUrl : f.baseUrl;
  if (url.isEmpty) return f.kind == NetworkFailureKind.noAnswer ? l.login_loadFailed : null;
  return switch (f.kind) {
    NetworkFailureKind.noAnswer => l.login_noAnswer(url),
    NetworkFailureKind.timeout => l.login_timeout(url),
    NetworkFailureKind.badBody => l.login_badBody(url),
    NetworkFailureKind.http => l.login_httpError(url, f.status ?? 0),
  };
}
```

## 2a. Session-end predicate, bytes and per-call timeouts

An app that answers 401 with a business code (for example "mail account not connected") must not sign the user out. Tell the client which 401s end the session:

```dart
ApiClient(
  baseUrl: base,
  http: client,
  tokens: tokens,
  // Only a 401 without a business code is a dead session.
  endsSession: (e) => !const {'mail_not_connected'}.contains(e.code),
);
```

The predicate runs on every 401 of a signed-in call, before and after a renewal. A throwing predicate is logged and counts as true. False means no renewal, no hook, and `Unauthorized` with the code kept. Without it every 401 ends the session, as before.

- `requestBytes('POST', path, body: {...}, accept: 'application/pdf')` sends JSON and returns the bytes. `getBytes` is unchanged.
- `timeout: Duration(...)` on `request`, the JSON helpers, `getBytes`, `requestBytes` and `openStream` sets the overall limit for that call (a long SSE turn needs it); the same methods take `headerTimeout:` for the header wait. `timeout` is the overall limit of a call. For a JSON or bytes call it covers the wait for the headers and the whole body read. `headerTimeout` is only the wait for the response headers, and it is never longer than `timeout`. For `openStream` (and `sse`) both bound the wait for the headers, and `timeout` also bounds reading an error body; once a 2xx answer has started, neither limits the stream (the SSE idle timeout does). Null for either uses the client's value.
- A 401 or 403 `{"detail": "text", "code": "x"}` now gives code `x` (before it gave `text`). A bare `{"detail": "not_invited"}` still gives `not_invited`.

## 3. Call-site changes

| Old | New | Find |
|---|---|---|
| `ApiClient(baseUrl: String, client: c)` | `ApiClient(baseUrl: Uri, http: c)` | `grep -rn "ApiClient(" flutterui` |
| `mapApiError(status, body)` (59 uses incl. tests) | `ErrorBody.parse(status, body)` | `grep -rn mapApiError flutterui` |
| A `SessionRefresh`, `TokenSource` (`auth/token_store.dart:4`) | import from `bond_api`; delete the local copies | `grep -rn "TokenSource" flutterui` |
| `get(path, bearer: t)` (4 uses, A) | send the token through `tokens`, or call `request` with a one-off client | `grep -rn "bearer: "` |
| `postMultipart(path, fileField:, filePath:)` (A 2, P 2) / `postMultipartBytes(...)` (A 7, P 3); counts include tests | `postMultipart(path, fields: {...}, files: [ApiFile(field:, filename:, bytes:)])` | `grep -rn postMultipart` |
| A `.sse(path, body:)` (`agent_stream_service.dart:67`) yields decoded maps | `.sse(...)` yields `SseEvent`; use `e.decoded` | |
| `ServerError(message, statusCode:)` | same, plus `code` | |

The exception names are the same (no edit needed; find them with `grep -rnwE "ApiException|NetworkFailure|Unauthorized|Forbidden|NotFound|Conflict|ValidationError|ServerError" flutterui`). `onSessionExpired` once meant renewal; grep for it.

## 4. Data

None. P's `ServerError` now carries `code` (`db_unavailable`); `bond_service_kit` sends it.

## 5. Acceptance
- A: `flutter test` in `packages/avalon_core` (`test/api/{api_client,robust_client,sse_client}_test.dart` move onto `MockClient`).
- P: `flutter test` in `packages/pt_core` (`test/api/`). Neither app has a test that two concurrent 401s call the renewal hook once: write it.
- `flutter analyze` clean. P's `networkFailureText` adapter is the same with `PtL10n` in place of `AvL10n`.

## 6. Known gaps (the app keeps these)
- Dropped from the seed client: web-socket helper, explicit-bearer mode, push-token path exemption, file-path multipart,
  `installGlobalErrorHooks` (stays in `error_hooks.dart`), localized strings (`ApiLabels`), `kIsWeb` (`isWeb:`).
- 405 and 429 map to `ServerError` with `statusCode`; there is no rate-limit class. `Conflict.existingDraftId` is gone: read `data`.
- S: `ErrorBody` now also reads `error_code` and a code-shaped `error` (servers should still send `code`), but treats every 401 with a token as session over; S's `PayloadTooLarge`
  (413) becomes `ServerError`, and `errorCode`/`details` become `code`/`data`. S waits for its backend to emit the shared body.
- Error code precedence is `code`, then `error_code`, then `error` (detail map first, then top level). The TODO routes send `code`
  (`docs/contracts/tasks.md`). S specifics: `sbel.md` §1 and §6.
