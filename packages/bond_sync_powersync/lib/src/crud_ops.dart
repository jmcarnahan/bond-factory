/// PowerSync CRUD entries as plain upload ops.
library;

import 'dart:convert';

import 'package:bond_sync/bond_sync.dart';

import 'sync_db.dart';

/// The write's `_metadata` JSON names the route (`action`) and may carry
/// fields that are not columns of the row (a share's target, a read cursor's
/// position): those ride in `data` next to the changed columns, which always
/// win on a name clash.
SyncUploadOp opFor(int seq, SyncCrudEntry e) {
  String? action;
  var data = e.opData ?? const <String, Object?>{};
  final meta = e.metadata;
  if (meta != null && meta.isNotEmpty) {
    try {
      final decoded = jsonDecode(meta);
      if (decoded is Map) {
        if (decoded['action'] is String) action = decoded['action'] as String;
        final extras = {
          for (final MapEntry(:key, :value) in decoded.entries)
            if (key is String && key != 'action' && !data.containsKey(key)) key: value,
        };
        if (extras.isNotEmpty) data = {...extras, ...data};
      }
    } catch (_) {
      action = null;
    }
  }
  return SyncUploadOp(seq: seq, op: e.op, table: e.table, id: e.id, action: action, data: data);
}

/// A transaction's key: stable across attempts.
String batchKey(SyncCrudTransaction tx) =>
    tx.transactionId != null ? 'tx${tx.transactionId}' : 'c${tx.entries.first.clientId}';

final RegExp sqlName = RegExp(r'^[a-z][a-z0-9_]*$');
