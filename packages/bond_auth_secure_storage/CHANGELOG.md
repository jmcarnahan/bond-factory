# Changelog

## 0.1.0 - unreleased
- New package, split out of `bond_signin_ui`: `SecureRefreshTokenStore`. Import it from
  `package:bond_auth_secure_storage/bond_auth_secure_storage.dart`. `bond_signin_ui` drops `flutter_secure_storage`
  (which kept a web app with `file_picker ^8` from resolving) and does not re-export the class.
