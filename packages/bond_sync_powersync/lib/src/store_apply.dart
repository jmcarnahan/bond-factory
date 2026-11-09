/// Applies the verdicts of one upload to the local database, in ONE transaction.
library;

import 'dart:convert';

import 'package:bond_sync/bond_sync.dart';

import 'crud_ops.dart';
import 'policy.dart';
import 'sync_db.dart';

/// Runs [planOutcome] against the database: re-keys rows the server re-keyed,
/// removes the optimistic row of a refused create, writes the refusal notes.
Future<void> applyOutcome(
  SyncDb db,
  SyncPolicy policy,
  List<SyncUploadOp> ops,
  Map<int, SyncVerdict> verdicts,
  DateTime now,
) async {
  final plan = planOutcome(ops, verdicts, now, rules: policy.rules);
  if (plan.isEmpty) return;
  final tables = policy.schemaTables;
  bool known(String t) => tables.contains(t) && sqlName.hasMatch(t);
  await db.writeTransaction((tx) async {
    for (final r in plan.rekeys) {
      if (known(r.op.table)) await _rekey(tx, policy, r.op.table, r.op.id, r.newId);
    }
    for (final f in plan.refusals) {
      var message = f.verdict.message;
      // The optimistic row never reached the server and never will. The raw
      // table is used on purpose: deleting through the view would queue a
      // DELETE upload for a row the server does not have.
      if (f.removeRow && known(f.op.table)) {
        try {
          await tx.execute('DELETE FROM ps_data__${f.op.table} WHERE id = ?', [f.op.id]);
          await _purgeFollowUps(tx, policy, f.op.table, f.op.id);
        } catch (_) {
          message = '${message ?? ''} (the unsent row could not be removed)'.trim();
        }
      }
      if (f.keepNote) await _insertNote(tx, f, message);
    }
  });
}

/// Once per (table, row, action, code): a retry after a failed complete()
/// must not add the note again.
Future<void> _insertNote(SyncSql tx, Refusal f, String? message) async {
  final op = f.op;
  final code = f.verdict.code ?? f.verdict.status;
  final stamp = f.stamp.toUtc().toIso8601String();
  final payload = jsonEncode(op.data);
  await tx.execute(
    'UPDATE sync_rejections SET message = ?, payload = ?, created_at = ?, op = ? '
    "WHERE table_name = ? AND row_id = ? AND ifnull(action, '') = ifnull(?, '') AND code = ?",
    [message, payload, stamp, op.op, op.table, op.id, op.action, code],
  );
  await tx.execute(
    'INSERT INTO sync_rejections (id, table_name, row_id, action, code, message, payload, created_at, op) '
    'SELECT ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS ('
    "SELECT 1 FROM sync_rejections WHERE table_name = ? AND row_id = ? AND ifnull(action, '') = ifnull(?, '') AND code = ?)",
    [newId(), op.table, op.id, op.action, code, message, payload, stamp, op.op, op.table, op.id, op.action, code],
  );
}

/// A create was refused: the writes still queued for the row and for the
/// child rows that name it can only fail with "not found". Drop them, and the
/// local child rows, so one cause raises one note.
Future<void> _purgeFollowUps(SyncSql tx, SyncPolicy policy, String table, String id) async {
  await tx.execute(
    "DELETE FROM ps_crud WHERE json_extract(data, '\$.type') = ? AND json_extract(data, '\$.id') = ?",
    [table, id],
  );
  for (final (child, column) in policy.rekeyChildren[table] ?? const <(String, String)>[]) {
    if (!sqlName.hasMatch(child) || !sqlName.hasMatch(column)) continue;
    await tx.execute(
      "DELETE FROM ps_crud WHERE json_extract(data, '\$.type') = ? AND json_extract(data, '\$.data.$column') = ?",
      [child, id],
    );
    await tx.execute("DELETE FROM ps_data__$child WHERE json_extract(data, '\$.$column') = ?", [id]);
  }
}

/// The server chose [newKey] for the row the device made as [oldKey]: re-key
/// the row, the child rows that name it and the writes still queued.
Future<void> _rekey(SyncSql tx, SyncPolicy policy, String table, String oldKey, String newKey) async {
  final exists = await tx.getOptional('SELECT 1 AS x FROM ps_data__$table WHERE id = ?', [newKey]);
  if (exists != null) {
    // The server's own copy already synced down: drop the local stand-in.
    await tx.execute('DELETE FROM ps_data__$table WHERE id = ?', [oldKey]);
  } else {
    await tx.execute('UPDATE ps_data__$table SET id = ? WHERE id = ?', [newKey, oldKey]);
  }
  await tx.execute(
    "UPDATE ps_crud SET data = json_set(data, '\$.id', ?) WHERE json_extract(data, '\$.type') = ? AND json_extract(data, '\$.id') = ?",
    [newKey, table, oldKey],
  );
  for (final (child, column) in policy.rekeyChildren[table] ?? const <(String, String)>[]) {
    if (!sqlName.hasMatch(child) || !sqlName.hasMatch(column)) continue;
    await tx.execute(
      "UPDATE ps_data__$child SET data = json_set(data, '\$.$column', ?) WHERE json_extract(data, '\$.$column') = ?",
      [newKey, oldKey],
    );
    await tx.execute(
      "UPDATE ps_crud SET data = json_set(data, '\$.data.$column', ?) WHERE json_extract(data, '\$.type') = ? AND json_extract(data, '\$.data.$column') = ?",
      [newKey, child, oldKey],
    );
  }
}
