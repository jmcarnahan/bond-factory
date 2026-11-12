# bond_auth_secure_storage

`SecureRefreshTokenStore`: keeps the rotating refresh token in the platform's secure storage (iOS keychain,
Android keystore) through `flutter_secure_storage`. It implements `RefreshTokenStore` from `bond_auth`.

```dart
import 'package:bond_auth_secure_storage/bond_auth_secure_storage.dart';

final store = SecureRefreshTokenStore(appKey: 'my_app', onError: (e) => log('secure write failed'));
```

- The key is `<appKey>.bond_refresh_token`. Give each app and flavour its own `appKey`.
- Reads are cached. `reload()` re-reads the stored value so two isolates share one token.
- A failed read keeps the cached value. A failed write keeps the value in the cache and goes to `onError`
  (never carries the token). Neither throws into a sign-in or a renewal.
- The in-flight rotation id is kept under `<appKey>.rotation`.
- Default storage: iOS and macOS "first unlock, this device only".

Why it is a separate package: `flutter_secure_storage` pulls a `win32` version on web that conflicts with
`file_picker ^8`. A web app that uses the sign-in widgets (`bond_signin_ui`) no longer links it. Add this package
only in an app that runs on a phone.
