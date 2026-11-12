# Changelog

## Unreleased
- BREAKING: `SecureRefreshTokenStore` moved to the new `bond_auth_secure_storage` package; no re-export. This package drops `flutter_secure_storage` (it kept a web app with `file_picker ^8` from resolving).
- `BondSignInScreen`, `BondSignInButtons`, `BondScopeAskCard`.
- `BrowserAuth` port with `defaultBrowserAuth()` (conditional import: top-level navigation on web, `flutter_web_auth_2` elsewhere) and `replaceAddress`.
- `NativeReturn.choose`: https return where the device supports it, else the custom scheme.
- `SecureRefreshTokenStore` over `flutter_secure_storage`.
- `SecureRefreshTokenStore`: `loadRotation`/`saveRotation` (key `<appKey>.rotation`), `onError` for failed writes. Scope card shows ask errors inline (`<prefix>.error`).
- `BondScopeAskCard`: each Allow button's accessible name includes the set ("Allow Calendar"); visible text unchanged.
