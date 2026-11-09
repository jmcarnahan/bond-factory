import 'dart:async';
import 'dart:convert';

import '../ids.dart';
import '../models.dart';
import '../outcome.dart';
import '../rejections.dart';
import '../store.dart';
import '../verdicts.dart';

class _Tx {
  _Tx(this.id, this.ops);
  final int id;
  final List<SyncUploadOp> ops;
}

/// An in-memory [SyncStore]: rows per table and a queue of local writes, one
/// transaction per write (or per [transaction] call). It applies verdicts with
/// the same [planOutcome] the database adapter uses.
class FakeSyncStore implements SyncStore {
  FakeSyncStore({this.rules = const OutcomeRules(), this.coalesce = false, DateTime Function()? now})
      : _now = now ?? DateTime.now;

  final OutcomeRules rules;

  /// When true, [nextBatch] answers ALL queued writes as one transaction with
  /// seq 0..n (a demo shows one verdict per row without clashing seq numbers).
  final bool coalesce;
  final DateTime Function() _now;

  final Map<String, Map<String, Map<String, Object?>>> _tables = {};
  final List<_Tx> _queue = [];
  final Map<String, String> _meta = {};
  final List<SyncRejection> _notes = [];
  final StreamController<List<SyncRejection>> _noteChanges = StreamController.broadcast();
  int _nextTx = 1;
  List<SyncUploadOp>? _open;

  /// Writes waiting to be sent (operations, not transactions).
  int get queuedOps => _queue.fold(0, (n, t) => n + t.ops.length);

  /// The queued operations, oldest first.
  List<SyncUploadOp> get queued => [for (final t in _queue) ...t.ops];

  Map<String, String> get meta => Map.unmodifiable(_meta);

  Map<String, Map<String, Object?>> _table(String t) => _tables.putIfAbsent(t, () => {});

  void _record(SyncUploadOp Function(int seq) make) {
    final open = _open;
    if (open != null) {
      open.add(make(open.length));
    } else {
      _queue.add(_Tx(_nextTx++, [make(0)]));
    }
  }

  /// Runs [body] so every write in it is ONE transaction.
  void transaction(void Function() body) {
    if (_open != null) throw StateError('transaction already open');
    _open = [];
    try {
      body();
    } finally {
      final ops = _open!;
      _open = null;
      if (ops.isNotEmpty) _queue.add(_Tx(_nextTx++, ops));
    }
  }

  /// Inserts or replaces a row and queues a `put`.
  void put(String table, String id, Map<String, Object?> data, {String? action}) {
    _table(table)[id] = {'id': id, ...data};
    _record((seq) => SyncUploadOp(seq: seq, op: 'put', table: table, id: id, action: action, data: {...data}));
  }

  /// Changes columns of a row and queues a `patch` with exactly those columns.
  void patch(String table, String id, Map<String, Object?> data, {String? action}) {
    final row = _table(table)[id];
    if (row != null) row.addAll(data);
    _record((seq) => SyncUploadOp(seq: seq, op: 'patch', table: table, id: id, action: action, data: {...data}));
  }

  void delete(String table, String id, {String? action}) {
    _table(table).remove(id);
    _record((seq) => SyncUploadOp(seq: seq, op: 'delete', table: table, id: id, action: action));
  }

  /// A row written by the server, with nothing queued.
  void putFromServer(String table, String id, Map<String, Object?> data) => _table(table)[id] = {'id': id, ...data};

  @override
  Future<SyncBatch?> nextBatch() async {
    if (_queue.isEmpty) return null;
    if (coalesce) {
      final txs = List.of(_queue);
      final all = [for (final t in txs) ...t.ops];
      return SyncBatch(
        key: 'tx${txs.first.id}',
        transactionId: txs.first.id,
        ops: [for (var i = 0; i < all.length; i++) _renumber(all[i], i)],
        complete: () async => _queue.removeWhere((t) => txs.any((x) => x.id == t.id)),
      );
    }
    final tx = _queue.first;
    return SyncBatch(
      key: 'tx${tx.id}',
      transactionId: tx.id,
      ops: [for (var i = 0; i < tx.ops.length; i++) _renumber(tx.ops[i], i)],
      complete: () async => _queue.removeWhere((t) => t.id == tx.id),
    );
  }

  SyncUploadOp _renumber(SyncUploadOp o, int seq) =>
      SyncUploadOp(seq: seq, op: o.op, table: o.table, id: o.id, action: o.action, data: o.data);

  @override
  Future<void> applyVerdicts(List<SyncUploadOp> ops, Map<int, SyncVerdict> verdicts, DateTime now) async {
    final plan = planOutcome(ops, verdicts, now, rules: rules);
    for (final r in plan.rekeys) {
      _rekey(r.op.table, r.op.id, r.newId);
    }
    for (final f in plan.refusals) {
      if (f.removeRow) _removeCreated(f.op.table, f.op.id);
      if (f.keepNote) _upsertNote(f);
    }
    if (plan.refusals.isNotEmpty) _noteChanges.add(List.of(_sorted()));
  }

  void _rekey(String table, String oldId, String newId) {
    final rows = _table(table);
    final old = rows.remove(oldId);
    if (rows.containsKey(newId)) {
      // The server's own copy is already here: the stand-in is dropped.
    } else if (old != null) {
      rows[newId] = {...old, 'id': newId};
    }
    for (final t in _queue) {
      for (var i = 0; i < t.ops.length; i++) {
        final o = t.ops[i];
        if (o.table == table && o.id == oldId) t.ops[i] = _with(o, id: newId);
      }
    }
    for (final (child, column) in rules.rekeyChildren[table] ?? const <(String, String)>[]) {
      for (final row in _table(child).values) {
        if (row[column] == oldId) row[column] = newId;
      }
      for (final t in _queue) {
        for (var i = 0; i < t.ops.length; i++) {
          final o = t.ops[i];
          if (o.table == child && o.data[column] == oldId) t.ops[i] = _with(o, data: {...o.data, column: newId});
        }
      }
    }
  }

  SyncUploadOp _with(SyncUploadOp o, {String? id, Map<String, Object?>? data}) =>
      SyncUploadOp(seq: o.seq, op: o.op, table: o.table, id: id ?? o.id, action: o.action, data: data ?? o.data);

  void _removeCreated(String table, String id) {
    _table(table).remove(id);
    _queue.removeWhere((t) {
      t.ops.removeWhere((o) => o.table == table && o.id == id);
      return t.ops.isEmpty;
    });
    for (final (child, column) in rules.rekeyChildren[table] ?? const <(String, String)>[]) {
      _table(child).removeWhere((_, row) => row[column] == id);
      _queue.removeWhere((t) {
        t.ops.removeWhere((o) => o.table == child && o.data[column] == id);
        return t.ops.isEmpty;
      });
    }
  }

  void _upsertNote(Refusal f) {
    final op = f.op;
    final code = f.verdict.code ?? f.verdict.status;
    final stamp = isoOf(f.stamp);
    final i = _notes.indexWhere(
      (n) => n.table == op.table && n.rowId == op.id && (n.action ?? '') == (op.action ?? '') && n.code == code,
    );
    final note = SyncRejection(
      id: i >= 0 ? _notes[i].id : newId(),
      table: op.table,
      rowId: op.id,
      action: op.action,
      code: code,
      message: f.verdict.message,
      payload: jsonEncode(op.data),
      createdAt: stamp,
      op: op.op,
    );
    if (i >= 0) {
      _notes[i] = note;
    } else {
      _notes.add(note);
    }
  }

  List<SyncRejection> _sorted() {
    final l = List.of(_notes)
      ..sort((a, b) {
        final c = a.createdAt.compareTo(b.createdAt);
        return c != 0 ? c : a.id.compareTo(b.id);
      });
    return l;
  }

  @override
  Future<String?> readMeta(String key) async => _meta[key];

  @override
  Future<void> writeMeta(String key, String value) async => _meta[key] = value;

  @override
  Future<void> deleteMeta(String key) async => _meta.remove(key);

  @override
  Future<void> pruneRejections(DateTime now) async {
    final cutoff = isoOf(now.subtract(kSyncRejectionKeep));
    _notes.removeWhere((n) => n.createdAt.compareTo(cutoff) < 0);
  }

  @override
  Future<List<SyncRejection>> rejections() async => _sorted();

  @override
  Future<void> clearRejection(String id) async {
    _notes.removeWhere((n) => n.id == id);
    _noteChanges.add(_sorted());
  }

  @override
  Stream<List<SyncRejection>> watchRejections() async* {
    yield _sorted();
    yield* _noteChanges.stream;
  }

  @override
  Future<SyncResendResult> resend(SyncRejection note) async {
    final op = note.op;
    if (note.rowId.isEmpty || (op != 'put' && op != 'patch')) return SyncResendResult.unsupported;
    Map<String, Object?>? data;
    try {
      final d = jsonDecode(note.payload ?? '');
      if (d is Map) data = d.cast<String, Object?>();
    } catch (_) {}
    if (data == null || data.isEmpty) return SyncResendResult.unsupported;
    final rows = _table(note.table);
    if (op == 'put') {
      final merged = {...(rows[note.rowId] ?? const {}), ...data}..remove('id');
      rows[note.rowId] = {'id': note.rowId, ...merged};
      _record((seq) =>
          SyncUploadOp(seq: seq, op: 'put', table: note.table, id: note.rowId, action: note.action, data: merged));
    } else {
      final row = rows[note.rowId];
      if (row == null) {
        final i = _notes.indexWhere((n) => n.id == note.id);
        if (i >= 0) {
          _notes[i] = _notes[i].copyWith(
            message: 'The change could not be sent again: the row is no longer on this device.',
          );
        }
        return SyncResendResult.rowGone;
      }
      row.addAll(data);
      _record((seq) =>
          SyncUploadOp(seq: seq, op: 'patch', table: note.table, id: note.rowId, action: note.action, data: data!));
    }
    _notes.removeWhere((n) => n.id == note.id);
    _noteChanges.add(_sorted());
    return SyncResendResult.queued;
  }

  @override
  Future<List<Map<String, Object?>>> rows(String table) async => [
        for (final r in _table(table).values) Map<String, Object?>.of(r),
      ];

  /// The clock the store was built with (a demo stamps its rows with it).
  DateTime now() => _now();

  void dispose() => _noteChanges.close();
}
