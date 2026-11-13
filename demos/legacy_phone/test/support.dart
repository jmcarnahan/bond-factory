import 'dart:async';
import 'dart:io';

import 'package:bond_sync_powersync/bond_sync_powersync.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_powersync/bond_tasks_powersync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:legacy_phone/legacy_phone.dart';
import 'package:powersync/powersync.dart';

import 'seed.dart';

/// 2026-03-11 13:00 in America/Los_Angeles (the Makefile exports TZ).
final DateTime kNow = DateTime.utc(2026, 3, 11, 20);

Future<List<SyncCrudEntry>> drain(SyncDb db) async {
  final out = <SyncCrudEntry>[];
  while (true) {
    final tx = await db.nextCrudTransaction();
    if (tx == null) return out;
    out.addAll(tx.entries);
    await tx.complete();
  }
}

/// A real local PowerSync database at one stage of the app's schema, seeded with the rows an old build wrote.
class LegacyEnv {
  LegacyEnv._(this.dir, this.stage, this.raw, this.db);

  final Directory dir;
  final LegacyStage stage;
  PowerSyncDatabase raw;
  SyncDb db;
  DateTime now = kNow;

  TaskClock get clock => TaskClock(() => now);

  PowerSyncTaskRepository repoFor([String user = 'u-owner', SyncDb? over]) =>
      legacyTaskRepository(over ?? db, userId: user, stage: stage, clock: clock);

  late final PowerSyncTaskRepository repo = repoFor();

  void tick([int minutes = 1]) => now = now.add(Duration(minutes: minutes));

  Future<SyncRow> row(String id) async => (await db.getOptional('SELECT * FROM tasks WHERE id = ?', [id]))!;

  Future<bool> exists(String id) async => await db.getOptional('SELECT id FROM tasks WHERE id = ?', [id]) != null;

  /// The columns of the `tasks` table at this stage (without `id`).
  Set<String> get columns => {for (final c in legacySchema(stage).tables.first.columns) c.name};

  Future<void> close() async {
    await raw.close();
    if (dir.existsSync()) dir.deleteSync(recursive: true);
  }
}

/// Opens the database at [LegacyStage.asShipped], seeds it, drains the seed's queue; for [LegacyStage.widened] it then
/// opens the SAME file again with the wider schema (old rows stay, the nine new columns read NULL).
Future<LegacyEnv> openEnv(LegacyStage stage, {bool seed = true}) async {
  final dir = Directory.systemTemp.createTempSync('legacy_phone');
  final path = '${dir.path}/t.db';
  var raw = PowerSyncDatabase(schema: legacySchema(LegacyStage.asShipped), path: path);
  await raw.initialize();
  if (seed) {
    await seedLegacy(raw);
    await drain(PowerSyncDb(raw));
  }
  if (stage == LegacyStage.widened) {
    await raw.close();
    raw = PowerSyncDatabase(schema: legacySchema(LegacyStage.widened), path: path);
    await raw.initialize();
  }
  return LegacyEnv._(dir, stage, raw, PowerSyncDb(raw));
}

/// Runs [body] once per stage; the database is closed afterwards.
void forEachStage(String name, Future<void> Function(LegacyEnv env) body, {bool seed = true}) {
  for (final stage in LegacyStage.values) {
    test('$name [${stage.name}]', () async {
      final env = await openEnv(stage, seed: seed);
      try {
        await body(env);
      } finally {
        await env.close();
      }
    });
  }
}

/// The first value of [s] that satisfies [ok]; subscribes at once, so start it before the write that causes it.
Future<T> nextWhere<T>(Stream<T> s, bool Function(T) ok) => s.firstWhere(ok).timeout(const Duration(seconds: 10));


/// What the connector would send for each queued CRUD transaction, drained: `[{user, body: {ops: [...]}}]`.
Future<List<Object?>> queuedRequests(LegacyEnv env) async {
  final store = PowerSyncSyncStore.withDb(
    env.db,
    policy: SyncPolicy(schema: legacySchema(env.stage)),
  );
  final out = <Object?>[];
  while (true) {
    final batch = await store.nextBatch();
    if (batch == null) return out;
    out.add({
      'user': 'u-owner',
      'body': {
        'ops': [for (final o in batch.ops) o.toJson()],
      },
    });
    await batch.complete();
  }
}

/// A subscription that keeps what it saw, for a re-emit test: await [first] (the OLD value), write, then await [next]
/// with the new value. It cannot pass without a real emission after the write.
class Watch<T> {
  Watch(Stream<T> s) {
    _sub = s.listen(seen.add);
  }
  final List<T> seen = [];
  late final StreamSubscription<T> _sub;
  int _mark = 0;

  Future<void> _until(bool Function() ok) async {
    final end = DateTime.now().add(const Duration(seconds: 10));
    while (!ok()) {
      if (DateTime.now().isAfter(end)) throw TimeoutException('no matching emission; saw ${seen.length}');
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
  }

  /// The first emission; later ones are "after" for [next].
  Future<T> first() async {
    await _until(() => seen.isNotEmpty);
    _mark = seen.length;
    return seen.first;
  }

  /// An emission after [first] that satisfies [ok].
  Future<T> next(bool Function(T) ok) async {
    await _until(() => seen.skip(_mark).any(ok));
    return seen.skip(_mark).firstWhere(ok);
  }

  Future<void> cancel() => _sub.cancel();
}

List<String> ids(Iterable<Task> tasks) => [for (final t in tasks) t.id];

/// A [SyncDb] that records the SQL it is asked to run (reads and writes).
class RecordingDb implements SyncDb {
  RecordingDb(this.inner);
  final SyncDb inner;
  final List<String> sql = [];

  SyncSql _wrap(SyncSql s) => _Rec(s, sql);

  @override
  Future<void> initialize() => inner.initialize();
  @override
  Future<void> execute(String q, [List<Object?> p = const []]) {
    sql.add(q);
    return inner.execute(q, p);
  }

  @override
  Future<List<SyncRow>> getAll(String q, [List<Object?> p = const []]) {
    sql.add(q);
    return inner.getAll(q, p);
  }

  @override
  Future<SyncRow?> getOptional(String q, [List<Object?> p = const []]) {
    sql.add(q);
    return inner.getOptional(q, p);
  }

  @override
  Future<T> writeTransaction<T>(Future<T> Function(SyncSql tx) body) => inner.writeTransaction((tx) => body(_wrap(tx)));
  @override
  Future<T> readTransaction<T>(Future<T> Function(SyncSql tx) body) => inner.readTransaction((tx) => body(_wrap(tx)));
  @override
  Stream<void> onChange(List<String> tables, {Duration throttle = const Duration(milliseconds: 30)}) =>
      inner.onChange(tables, throttle: throttle);
  @override
  Stream<List<SyncRow>> watch(String q, [List<Object?> p = const []]) => inner.watch(q, p);
  @override
  Future<SyncCrudTransaction?> nextCrudTransaction() => inner.nextCrudTransaction();
  @override
  Future<void> disconnect() => inner.disconnect();
  @override
  Future<void> close() => inner.close();
}

class _Rec implements SyncSql {
  _Rec(this.inner, this.sql);
  final SyncSql inner;
  final List<String> sql;
  @override
  Future<void> execute(String q, [List<Object?> p = const []]) {
    sql.add(q);
    return inner.execute(q, p);
  }

  @override
  Future<List<SyncRow>> getAll(String q, [List<Object?> p = const []]) {
    sql.add(q);
    return inner.getAll(q, p);
  }

  @override
  Future<SyncRow?> getOptional(String q, [List<Object?> p = const []]) {
    sql.add(q);
    return inner.getOptional(q, p);
  }
}
