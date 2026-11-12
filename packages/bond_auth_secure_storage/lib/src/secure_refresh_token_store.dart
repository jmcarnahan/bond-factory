import 'package:bond_auth/bond_auth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keeps the rotating refresh token in the platform's secure storage (iOS
/// keychain, Android keystore) so the apps write no storage code.
///
/// The key is `<appKey>.bond_refresh_token`; give each app (and flavour) its
/// own [appKey]. Reads are cached; [reload] re-reads the stored value so two
/// isolates share one token. A storage read that fails keeps the cached value
/// instead of throwing into the renewal. A failed write keeps the value in the
/// cache (the session still works until the app restarts) and is reported
/// through [onError]; it never throws into a sign-in or a renewal. The
/// in-flight rotation id is kept under `<appKey>.rotation`.
class SecureRefreshTokenStore implements RefreshTokenStore {
  SecureRefreshTokenStore({
    required this.appKey,
    FlutterSecureStorage storage = defaultStorage,
    this.onError,
  }) : _storage = storage;

  /// First unlock, this device only: background renewals work with the phone
  /// locked after a restart, and the token never leaves the device in a backup.
  static const FlutterSecureStorage defaultStorage = FlutterSecureStorage(
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
    mOptions: MacOsOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
  );

  final String appKey;
  final FlutterSecureStorage _storage;

  /// Told about a storage write that failed (never carries the token).
  final void Function(Object error)? onError;

  String? _cache;
  String? _rotation;
  bool _loaded = false;
  bool _rotationLoaded = false;

  String get _key => '$appKey.bond_refresh_token';
  String get _rotationKey => '$appKey.rotation';

  Future<void> _write(String key, String? value) async {
    try {
      await _storage.write(key: key, value: value);
    } on Object catch (e) {
      try {
        onError?.call(e);
      } on Object {
        // A faulty reporter must not break sign-in.
      }
    }
  }

  @override
  Future<String?> load() async {
    if (!_loaded) await reload();
    return _cache;
  }

  @override
  Future<void> reload() async {
    try {
      final v = await _storage.read(key: _key);
      _cache = v == null || v.isEmpty ? null : v;
    } on Object {
      // Keep what we have; the server decides if it is still good.
    }
    _loaded = true;
  }

  @override
  Future<void> save(String token) async {
    _cache = token;
    _loaded = true;
    await _write(_key, token);
  }

  @override
  Future<void> clear() async {
    _cache = null;
    _rotation = null;
    _loaded = true;
    _rotationLoaded = true;
    await _write(_key, null);
    await _write(_rotationKey, null);
  }

  @override
  Future<String?> loadRotation() async {
    if (!_rotationLoaded) {
      try {
        final v = await _storage.read(key: _rotationKey);
        _rotation = v == null || v.isEmpty ? null : v;
      } on Object {
        // No saved id: the next rotation makes a fresh one.
      }
      _rotationLoaded = true;
    }
    return _rotation;
  }

  @override
  Future<void> saveRotation(String? id) async {
    _rotation = id;
    _rotationLoaded = true;
    await _write(_rotationKey, id);
  }
}
