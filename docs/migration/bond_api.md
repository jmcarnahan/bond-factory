# Migrating to bond_api

`ApiClient`, the typed `ApiException` family, `ErrorBody.parse`, SSE and `networkFailureText`
(`packages/bond_api`, pure Dart). Needs `bond_json` through the same SHA. Legend: `docs/migration/README.md`.

## 1. What it replaces

Paths are under `flutterui/packages/<core>/lib/src/api/` (A `avalon_core`, P `pt_core`).

| App | Goes away | Shrinks or stays |
|---|---|---|
| A | `api_client.dart` 509, `api_exception.dart` 173, `sse.dart` 32 | `network_failure_text.dart` 20 becomes an adapter; `error_hooks.dart` 25 stays (Flutter); `avalon_api.dart` 2,206 keeps its 218 `_client.<verb>(` calls |
| P | `api_client.dart` 367, `api_exception.dart` 148 | `network_failure_text.dart` 20 adapter; `error_hooks.dart` 25 and `device_anchor.dart` 18 stay; `paga_api.dart` 1,565 keeps 123 verb calls |
| S | phone `mobile/crm_proposals/lib/core/api/{api_client 178, api_exception 76}.dart`, `SseFrameSplitter` in `lib/data/calendar_assistant/stream.dart:14` | web has no client (45 services use `package:http`): later |

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

`networkFailureText` adapter (A keeps its `AvL10n` strings; bond's returns a sentence always, A's returned null):

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

## 3. Call-site changes

| Old | New | Find |
|---|---|---|
| `ApiClient(baseUrl: String, client: c)` | `ApiClient(baseUrl: Uri, http: c)` | `grep -rn "ApiClient(" flutterui` |
| `mapApiError(status, body)` (59 uses incl. tests) | `ErrorBody.parse(status, body)` | `grep -rn mapApiError flutterui` |
| A `SessionRefresh`, `TokenSource` (`auth/token_store.dart:4`) | import from `bond_api`; delete the local copies | `grep -rn "TokenSource" flutterui` |
| `get(path, bearer: t)` (4 uses, A) | send the token through `tokens`, or call `request` with a one-off client | `grep -rn "bearer: "` |
| `postMultipart(path, fileField:, filePath:)` (2) / `postMultipartBytes(...)` (5) | `postMultipart(path, fields: {...}, files: [ApiFile(field:, filename:, bytes:)])` | `grep -rn postMultipart` |
| A `.sse(path, body:)` (`agent_stream_service.dart:67`) yields decoded maps | `.sse(...)` yields `SseEvent`; use `e.decoded` | |
| `ServerError(message, statusCode:)` | same, plus `code` | |

The exception names are the same (1,104 uses in A need no edit). `onSessionExpired` once meant renewal; grep for it.

## 4. Data

None. P's `ServerError` now carries `code` (`db_unavailable`); `bond_service_kit` sends it.

## 5. Acceptance

- A: `flutter test` in `packages/avalon_core` (`test/api/{api_client,robust_client,sse_client}_test.dart` move onto `MockClient`).
- P: `flutter test` in `packages/pt_core` (`test/api/`). Both: a test that two concurrent 401s call the renewal hook once.
- `flutter analyze` clean. P's `networkFailureText` adapter is the same with `PtL10n` in place of `AvL10n`.

## 6. Known gaps (the app keeps these)

- Dropped from the seed client: web-socket helper, explicit-bearer mode, push-token path exemption, file-path multipart,
  `installGlobalErrorHooks` (stays in `error_hooks.dart`), localized strings (`ApiLabels`), `kIsWeb` (`isWeb:`).
- 405 and 429 map to `ServerError` with `statusCode`; there is no rate-limit class. `Conflict.existingDraftId` is gone: read `data`.
- S: `ErrorBody` reads `code`, not `error_code`, and treats every 401 with a token as session over; S's `PayloadTooLarge`
  (413) becomes `ServerError`, and `errorCode`/`details` become `code`/`data`. S waits for its backend to emit the shared body.
