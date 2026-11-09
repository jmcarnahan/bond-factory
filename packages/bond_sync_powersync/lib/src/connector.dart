/// Gets credentials for the sync service and uploads the device's queued writes.
library;

import 'package:bond_sync/bond_sync.dart';
import 'package:powersync/powersync.dart';

import 'policy.dart';
import 'store.dart';

/// Credentials: a sync token from the server; on `unauthorized` the session is
/// renewed once and the token asked for again. A [StateError] when no endpoint
/// is known. Uploads: [SyncUploader] over a [PowerSyncSyncStore]; the outcome
/// rules are documented there. Uploading never throws for a permanent outcome
/// and never crashes on a surprise: anything that must be retried reaches the
/// SDK as a plain [Exception], so it backs off and calls again.
class SyncConnector extends PowerSyncBackendConnector {
  SyncConnector({
    required this.transport,
    this.mapFailure = mapSyncFailure,
    required this.clock,
    required this.policy,
    this.onServerNow,
  });

  final SyncTransport transport;
  final FailureMapper mapFailure;
  final ServerClock clock;
  final SyncPolicy policy;

  /// Told the server's clock after every answer that carries it.
  final void Function(DateTime serverNow)? onServerNow;

  PowerSyncDatabase? _database;
  PowerSyncSyncStore? _databaseStore;
  SyncUploader? _uploader;
  SyncStore? _uploaderStore;

  @override
  Future<PowerSyncCredentials?> fetchCredentials() async {
    SyncToken t;
    try {
      t = await transport.fetchToken();
    } catch (e) {
      if (mapFailure(e) != SyncFailure.unauthorized) rethrow;
      if (await transport.refreshSession() != SessionRefresh.renewed) rethrow;
      t = await transport.fetchToken();
    }
    final now = t.serverNow;
    if (now != null) {
      clock.note(now);
      onServerNow?.call(now);
    }
    final endpoint = policy.endpointOverride ?? t.endpoint;
    if (endpoint == null || endpoint.isEmpty) {
      throw StateError('The server did not name a sync endpoint.');
    }
    return PowerSyncCredentials(endpoint: endpoint, token: t.token, expiresAt: t.expiresAt);
  }

  @override
  Future<void> uploadData(PowerSyncDatabase database) {
    // One store (and so one uploader, with its in-memory verdicts) per database.
    if (!identical(_database, database)) {
      _database = database;
      _databaseStore = PowerSyncSyncStore(database, policy: policy);
    }
    return uploadWith(_databaseStore!);
  }

  /// Uploads the oldest queued transaction from [store]. The body of
  /// [uploadData], open so a test can pass a store without a database.
  Future<void> uploadWith(SyncStore store) async {
    try {
      if (!identical(_uploaderStore, store)) {
        _uploaderStore = store;
        _uploader = SyncUploader(
          store: store,
          transport: transport,
          clock: clock,
          mapFailure: mapFailure,
          limits: policy.limits,
          rules: policy.rules,
          sendableTables: policy.sendableTables,
          onServerNow: onServerNow,
        );
      }
      await _uploader!.uploadNext();
    } catch (_) {
      // Whatever it was, the SDK backs off and calls again.
      throw Exception('transient');
    }
  }
}
