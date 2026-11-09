/// The wire between the uploader and the server. Nothing else in the core
/// knows how a request is made.
library;

import 'package:bond_api/bond_api.dart';

import 'models.dart';

export 'package:bond_api/bond_api.dart' show SessionRefresh;

abstract class SyncTransport {
  /// A sync token for the signed-in person.
  Future<SyncToken> fetchToken();

  /// Sends one chunk of queued writes.
  Future<UploadResponse> upload(UploadRequest request);

  /// Renews the session without touching sign-in state. Never signs the person out.
  Future<SessionRefresh> refreshSession();
}

/// [SyncTransport] over an [ApiClient]: `POST /sync/token`, `POST /sync/upload`.
///
/// Give sync a client WITHOUT `onUnauthorized`/`onSessionExpired` hooks that
/// sign the person out: a 401 on a background upload must reach the uploader,
/// which calls [refreshSession] and sends once more. [renewal] does the
/// renewing; without it the client's own `onUnauthorized` is used, and without
/// either the answer is `rejected`.
///
/// The paths are the app's choice (`docs/contracts/sync_upload.md`): pass
/// [tokenPath] and [uploadPath] when the app mounts the routes elsewhere.
class ApiSyncTransport implements SyncTransport {
  ApiSyncTransport(
    this._api, {
    Future<SessionRefresh> Function()? renewal,
    this.tokenPath = '/sync/token',
    this.uploadPath = '/sync/upload',
  }) : _renewal = renewal;

  final ApiClient _api;
  final Future<SessionRefresh> Function()? _renewal;
  final String tokenPath;
  final String uploadPath;

  @override
  Future<SyncToken> fetchToken() async => SyncToken.fromJson(await _api.postJson(tokenPath));

  @override
  Future<UploadResponse> upload(UploadRequest request) async =>
      UploadResponse.fromJson(await _api.postJson(uploadPath, body: request.toJson()));

  @override
  Future<SessionRefresh> refreshSession() async {
    final hook = _renewal ?? _api.onUnauthorized;
    if (hook == null) return SessionRefresh.rejected;
    try {
      return await hook();
    } catch (_) {
      return SessionRefresh.rejected;
    }
  }
}
