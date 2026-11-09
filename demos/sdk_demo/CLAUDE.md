# sdk_demo
Role: Flutter web harness for every bond SDK package. Never shipped.

## Commands
- `make test T=test/smoke_test.dart`
- `make analyze`
- `make serve-web` (debug web-server on :8078)

## Rules
- No popups, dialogs or modal sheets; show state inline.
- No codegen.
- Depend on packages by pubspec `path:` only.
- 300-line soft cap per source file.
