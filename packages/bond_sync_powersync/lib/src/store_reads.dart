/// Reactive reads over the local database.
library;

import 'dart:async';

import 'sync_db.dart';

/// The names to hand `onChange` for [tables]: the view and its raw `ps_data__`
/// table (a write through the view and a sync delivery land on different
/// names, and a reader that lists only one renders stale rows). [localOnly]
/// tables get the view and `ps_data_local__`. [crud] adds `ps_crud`, but that
/// misses the deletes the SDK makes on its own connection after an upload; use
/// `watch` with a `ps_crud` trigger for that.
List<String> changeTargets(
  Iterable<String> tables, {
  Iterable<String> localOnly = const [],
  bool crud = false,
}) =>
    [
      for (final t in tables) ...[t, 'ps_data__$t'],
      for (final t in localOnly) ...[t, 'ps_data_local__$t'],
      if (crud) 'ps_crud',
    ];

/// A pulse each time any of [tables] (or [localOnly], or `ps_crud`) changes.
Stream<void> storeChanges(
  SyncDb db,
  Iterable<String> tables, {
  Iterable<String> localOnly = const [],
  bool crud = false,
  Duration throttle = const Duration(milliseconds: 30),
}) =>
    db.onChange(changeTargets(tables, localOnly: localOnly, crud: crud), throttle: throttle);

/// One consistent snapshot: [read] gets the transaction's SQL access.
Future<T> readSnapshot<T>(SyncDb db, Future<T> Function(SyncSql sql) read) => db.readTransaction(read);

/// A live snapshot: [read] runs once now and again after every change to
/// [tables] (view and raw table both), the latest result always winning.
Stream<T> watchSnapshot<T>(
  SyncDb db,
  Iterable<String> tables,
  Future<T> Function(SyncSql sql) read, {
  Iterable<String> localOnly = const [],
  bool crud = false,
  Duration throttle = const Duration(milliseconds: 30),
}) {
  late final StreamController<T> controller;
  StreamSubscription<void>? sub;
  var seq = 0;
  var closed = false;

  Future<void> run() async {
    final mine = ++seq;
    try {
      final value = await readSnapshot(db, read);
      if (closed || mine != seq) return;
      controller.add(value);
    } catch (e, st) {
      if (closed || mine != seq) return;
      controller.addError(e, st);
    }
  }

  controller = StreamController<T>(
    onListen: () {
      sub = storeChanges(db, tables, localOnly: localOnly, crud: crud, throttle: throttle).listen((_) => run());
      unawaited(run());
    },
    onCancel: () async {
      closed = true;
      await sub?.cancel();
    },
  );
  return controller.stream;
}
