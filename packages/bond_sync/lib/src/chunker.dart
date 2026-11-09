/// Splits ops into requests that fit the limits.
library;

import 'dart:convert';

import 'limits.dart';
import 'models.dart';

/// Splits [ops] into requests of at most `limits.chunkSize` ops and
/// `limits.chunkBytes` JSON bytes, keeping to the per-kind caps in
/// `limits.sendCaps` (kind = `table:action`).
List<List<SyncUploadOp>> chunkOps(List<SyncUploadOp> ops, UploadLimits limits) {
  final out = <List<SyncUploadOp>>[];
  var cur = <SyncUploadOp>[];
  var counts = <String, int>{};
  var bytes = 0;
  for (final op in ops) {
    final kind = '${op.table}:${op.action ?? ''}';
    final cap = limits.sendCaps[kind];
    final size = utf8.encode(jsonEncode(op.toJson())).length + 1;
    final full = cur.isNotEmpty &&
        (bytes + size > limits.chunkBytes ||
            cur.length >= limits.chunkSize ||
            (cap != null && (counts[kind] ?? 0) >= cap));
    if (full) {
      out.add(cur);
      cur = <SyncUploadOp>[];
      counts = <String, int>{};
      bytes = 0;
    }
    bytes += size;
    cur.add(op);
    counts[kind] = (counts[kind] ?? 0) + 1;
  }
  if (cur.isNotEmpty) out.add(cur);
  return out;
}
