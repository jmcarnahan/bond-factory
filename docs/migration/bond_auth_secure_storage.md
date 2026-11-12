# Migrating to bond_auth_secure_storage

`SecureRefreshTokenStore` over `flutter_secure_storage` (`packages/bond_auth_secure_storage`). Split out of
`bond_signin_ui` on 2026-11-12. Context: `bond_signin.md`. Legend: `docs/migration/README.md`.

## 1. Why a package of its own

On web, `flutter_secure_storage ^11` pulls `win32 ^6`. `file_picker ^8` needs `win32 ^5`. An app with both failed `pub get`,
which kept a web app off the sign-in widgets. Now `bond_signin_ui` does not depend on the storage plugin, so a web app
resolves with `file_picker ^8`.

## 2. What the app does

- Phone app: add `bond_auth_secure_storage` to the pubspec (git ref, `path: packages/bond_auth_secure_storage`) and change
  the import:
  - Old: `import 'package:bond_signin_ui/bond_signin_ui.dart';`
  - New: `import 'package:bond_auth_secure_storage/bond_auth_secure_storage.dart';`
  `bond_signin_ui` no longer exports `SecureRefreshTokenStore`, so an old import of it fails to compile.
- Web app: add nothing. Use `NoRefreshTokenStore` (`import 'package:bond_auth/bond_auth.dart';`) or the cookie session.
- An app that builds for web and phone from one pubspec still pulls the plugin. Put the store behind a conditional import or
  a separate phone entry point if the conflict matters there.

## 3. What to test

`make -C packages/bond_auth_secure_storage test` and `analyze`. Checked once by hand on 2026-11-12 in a
scratch web consumer with `bond_signin_ui` and `file_picker: ^8.0.0`: `flutter pub get` succeeded (it failed before the
split). No CI job repeats it. `tool/boundary_gate.sh` does track the rule that only this package depends on
`flutter_secure_storage`. To check your own app, run `flutter pub get`, then `flutter pub deps` and look for
`flutter_secure_storage`.
