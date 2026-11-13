/// Opening the local database with a recovery ladder.
library;

import 'dart:async';
import 'dart:developer' as developer;

import 'package:bond_sync/bond_sync.dart';
import 'package:powersync/powersync.dart';

import 'policy.dart';
import 'store.dart';
import 'store_files_stub.dart' if (dart.library.io) 'store_files_io.dart';
import 'sync_db.dart';

/// The `sync_meta` key that holds when the local copy was reset (a moved-aside store).
const String kSyncStoreResetKey = 'store_reset';

/// The local database could not be opened, not even after starting over.
class SyncOpenFailure implements Exception {
  SyncOpenFailure(this.cause);

  /// What the last attempt threw.
  final Object cause;

  @override
  String toString() => 'SyncOpenFailure($cause)';
}

/// What an open produced.
class SyncStoreOpen {
  const SyncStoreOpen(this.db, this.store, {this.movedAside = false});

  final SyncDb db;
  final PowerSyncSyncStore store;

  /// The old files were damaged and were put aside; this store is empty.
  final bool movedAside;

  /// The real database to `connect()`, when [db] is a [PowerSyncDb].
  PowerSyncDatabase? get powerSync => switch (db) {
        PowerSyncDb(:final database) => database,
        _ => null,
      };
}

typedef SyncDbFactory = SyncDb Function(Schema schema, String path);

SyncDb _powerSyncFactory(Schema schema, String path) => PowerSyncDb(PowerSyncDatabase(schema: schema, path: path));

/// Opens the database at [path] with a ladder: open; on failure wait and try
/// the SAME files again; on a second failure move them aside (never deleted: a
/// queue in them may be recoverable) and start fresh; a third failure throws
/// [SyncOpenFailure].
Future<SyncStoreOpen> openSyncStore({
  required SyncPolicy policy,
  required String path,
  BondSyncNames names = const BondSyncNames(),
  Duration retryDelay = const Duration(seconds: 1),
  Duration closeTimeout = const Duration(seconds: 5),
  SyncDbFactory? dbFactory,
  DateTime Function()? now,
}) =>
    SyncStoreOpener(
      policy: policy,
      names: names,
      retryDelay: retryDelay,
      closeTimeout: closeTimeout,
      dbFactory: dbFactory,
      now: now,
    ).open(path);

class SyncStoreOpener {
  SyncStoreOpener({
    required this.policy,
    this.names = const BondSyncNames(),
    this.retryDelay = const Duration(seconds: 1),
    this.closeTimeout = const Duration(seconds: 5),
    SyncDbFactory? dbFactory,
    DateTime Function()? now,
  })  : _factory = dbFactory ?? _powerSyncFactory,
        _now = now ?? DateTime.now;

  final SyncPolicy policy;
  final BondSyncNames names;
  final Duration retryDelay;
  final Duration closeTimeout;
  final SyncDbFactory _factory;
  final DateTime Function() _now;

  void _log(String text, Object error, StackTrace st) =>
      developer.log(text, name: names.loggerName, error: error, stackTrace: st);

  Future<SyncStoreOpen> open(String path) async {
    var db = _factory(policy.schema, path);
    var movedAside = false;
    try {
      await db.initialize();
    } catch (e, st) {
      _log('local store did not open; trying again', e, st);
      await closeQuietly(db).timeout(closeTimeout, onTimeout: () {});
      await Future<void>.delayed(retryDelay);
      db = _factory(policy.schema, path);
      try {
        await db.initialize();
      } catch (e2, st2) {
        await closeQuietly(db).timeout(closeTimeout, onTimeout: () {});
        final aside = moveAside(path);
        _log('local store did not open twice; moved aside: ${aside.length} file(s)', e2, st2);
        movedAside = aside.isNotEmpty;
        db = _factory(policy.schema, path);
        try {
          await db.initialize();
        } catch (e3, st3) {
          _log('local store did not open after starting over', e3, st3);
          await closeQuietly(db).timeout(closeTimeout, onTimeout: () {});
          throw SyncOpenFailure(e3);
        }
      }
    }
    final store = PowerSyncSyncStore.withDb(db, policy: policy);
    if (movedAside) {
      try {
        await store.writeMeta(kSyncStoreResetKey, _now().toUtc().toIso8601String());
      } catch (_) {}
    }
    try {
      await store.pruneRejections(_now());
    } catch (_) {}
    return SyncStoreOpen(db, store, movedAside: movedAside);
  }

  /// Renames a database file and its `-wal`, `-shm` and `-journal` siblings to
  /// `<name>.bad-<unix ms>`. Returns the renamed paths. Never throws, never
  /// deletes (except older moved-aside copies, after the new rename worked).
  ///
  /// On the web this does nothing and returns an empty list (no file is moved); it does not report that.
  List<String> moveAside(String base) {
    final moved = renameAside(base, _now().millisecondsSinceEpoch);
    if (moved.isNotEmpty) deleteMovedAside(base, keep: moved.toSet());
    return moved;
  }

  /// Deletes every `<db>.bad-*` file (and sibling) of the database at [base].
  ///
  /// On the web this does nothing, silently.
  static void deleteMovedAside(String base, {Set<String> keep = const {}}) => removeMovedAside(base, keep);
}

/// Ends the connection, THEN closes the file: closing under a live connection
/// makes the SDK report on a closed status stream.
Future<void> closeQuietly(SyncDb db) async {
  try {
    await db.disconnect();
  } catch (_) {}
  try {
    await db.close();
  } catch (_) {}
}

/// Deletes the database file at [base] with its `-wal`, `-shm`, `-journal`
/// siblings and any moved-aside copies.
///
/// On the web this does NOTHING, silently: it does not wipe local data there. Clear a web store with the sync SDK
/// (`PowerSyncDatabase.disconnectAndClear`).
void deleteStoreFiles(String base) {
  removeDbFiles(base);
  SyncStoreOpener.deleteMovedAside(base);
}
