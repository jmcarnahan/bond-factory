/// Queues a refused write again.
library;

import 'dart:convert';

import 'package:bond_sync/bond_sync.dart';

import 'crud_ops.dart';
import 'policy.dart';
import 'sync_db.dart';

/// Queues a refused write again: the SAME operation, with the SAME row id and
/// the same data. The note's payload is the record of the write, never the
/// local row: after a checkpoint the server's state overwrites the optimistic
/// row and removes one the server never had.
///
///  * `put`: `INSERT OR REPLACE` through the table's view, which queues a PUT.
///    The row the device holds now is merged under the payload.
///  * `patch`: the payload's columns are first knocked out of the stored row
///    (a raw write, nothing queued), so the following `UPDATE` really changes
///    them and queues a PATCH with exactly those columns.
///
/// Table and column names come from the schema, never from the note. Writes
/// whose extras are not columns cannot be rebuilt: `unsupported`.
Future<SyncResendResult> resendNote(SyncDb db, SyncPolicy policy, SyncRejection note) {
  return db.writeTransaction((tx) => _one(tx, policy, note));
}

Future<SyncResendResult> _one(SyncSql tx, SyncPolicy policy, SyncRejection note) async {
  final tables = {
    for (final t in policy.schema.tables)
      if (!t.localOnly && !policy.notUploadedTables.contains(t.name)) t.name: t,
  };
  final table = tables[note.table];
  if (table == null || !sqlName.hasMatch(note.table) || note.rowId.isEmpty) {
    return SyncResendResult.unsupported;
  }
  final op = note.op;
  if (op != 'put' && op != 'patch') return SyncResendResult.unsupported;
  final data = _payload(note.payload);
  if (data == null || data.isEmpty) return SyncResendResult.unsupported;
  final allowed = {for (final c in table.columns) c.name};
  for (final k in data.keys) {
    if (!sqlName.hasMatch(k) || !allowed.contains(k)) return SyncResendResult.unsupported;
  }
  final withMeta = table.trackMetadata && note.action != null;
  final meta = withMeta ? jsonEncode({'action': note.action}) : null;

  if (op == 'put') {
    final merged = <String, Object?>{};
    final current = await tx.getOptional('SELECT data FROM ps_data__${note.table} WHERE id = ?', [note.rowId]);
    final raw = _payload(current?['data'] as String?);
    if (raw != null) {
      for (final e in raw.entries) {
        if (allowed.contains(e.key)) merged[e.key] = e.value;
      }
    }
    merged.addAll(data);
    final keys = merged.keys.toList();
    await tx.execute(
      'INSERT OR REPLACE INTO ${note.table} (id, ${keys.join(', ')}${withMeta ? ', _metadata' : ''}) '
      'VALUES (?, ${List.filled(keys.length, '?').join(', ')}${withMeta ? ', ?' : ''})',
      [note.rowId, for (final k in keys) _value(merged[k]), if (withMeta) meta],
    );
  } else {
    final keys = data.keys.toList();
    final values = [for (final k in keys) _value(data[k])];
    final row = await tx.getOptional('SELECT 1 AS x FROM ps_data__${note.table} WHERE id = ?', [note.rowId]);
    if (row == null) {
      await tx.execute('UPDATE sync_rejections SET message = ? WHERE id = ?', [
        'The change could not be sent again: the row is no longer on this device.',
        note.id,
      ]);
      return SyncResendResult.rowGone;
    }
    // Knock the payload's columns out of the stored row so the UPDATE below
    // really changes them (an UPDATE that changes nothing queues nothing).
    var raw = 'data';
    final paths = <String>[];
    for (var i = 0; i < keys.length; i++) {
      paths.add('\$.${keys[i]}');
      raw = values[i] == null ? 'json_set($raw, ?, 0)' : 'json_remove($raw, ?)';
    }
    await tx.execute('UPDATE ps_data__${note.table} SET data = $raw WHERE id = ?', [...paths, note.rowId]);
    await tx.execute(
      'UPDATE ${note.table} SET ${keys.map((k) => '$k = ?').join(', ')}${withMeta ? ', _metadata = ?' : ''} WHERE id = ?',
      [...values, if (withMeta) meta, note.rowId],
    );
  }
  await tx.execute('DELETE FROM sync_rejections WHERE id = ?', [note.id]);
  return SyncResendResult.queued;
}

Map<String, Object?>? _payload(String? raw) {
  if (raw == null || raw.isEmpty) return null;
  try {
    final d = jsonDecode(raw);
    return d is Map ? d.cast<String, Object?>() : null;
  } catch (_) {
    return null;
  }
}

/// A value as the stored column holds it.
Object? _value(Object? v) => switch (v) {
      null || num() || String() => v,
      bool() => v ? 1 : 0,
      _ => jsonEncode(v),
    };
