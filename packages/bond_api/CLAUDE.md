# bond_api
Role: HTTP `ApiClient`, typed exception family, error-body parser, SSE parser, failure text. Pure Dart over `package:http`.

## Key files
- `lib/src/client.dart`: request loop, timeouts, 401 renewal, session hooks. `client_session.dart` (part): shared renewal, session-end hooks. `client_requests.dart`: JSON verbs.
- `lib/src/error_body.dart`, `exceptions.dart`: `ErrorBody.parse`, the exception family.
- `lib/src/sse.dart`, `multipart.dart`, `labels.dart`, `network_failure_text.dart`, `token_source.dart`.

## Commands
- `make test T=test/client_test.dart`
- `make analyze`

## Rules
- No Flutter, no `dart:io`; no dependency on bond_auth (it implements `TokenSource`).
- 401: renew once, replay exactly once; auth paths never renew; never log tokens or bodies.
- Tests use `MockClient` from `package:http/testing.dart`.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
