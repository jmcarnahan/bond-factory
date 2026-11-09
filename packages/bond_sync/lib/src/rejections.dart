/// Refused writes kept for the person to see next to the row.
library;

import 'store.dart';

/// How long a note stays before it is cleared on its own.
const Duration kSyncRejectionKeep = Duration(days: 30);

/// One upload the server refused. Shown inline next to the row until the
/// person clears it or resends.
class SyncRejection {
  const SyncRejection({
    required this.id,
    required this.table,
    required this.rowId,
    required this.action,
    required this.code,
    required this.message,
    required this.payload,
    required this.createdAt,
    this.op,
  });

  /// Reads a `sync_rejections` row (`table_name`, `row_id`, ...).
  factory SyncRejection.fromRow(Map<String, Object?> row) => SyncRejection(
        id: row['id']! as String,
        table: (row['table_name'] as String?) ?? '',
        rowId: (row['row_id'] as String?) ?? '',
        action: row['action'] as String?,
        code: (row['code'] as String?) ?? '',
        message: row['message'] as String?,
        payload: row['payload'] as String?,
        createdAt: (row['created_at'] as String?) ?? '',
        op: row['op'] as String?,
      );

  final String id;
  final String table;
  final String rowId;
  final String? action;

  /// The server's reason (`forbidden`, `conflict`, `upload_rejected`, ...).
  final String code;
  final String? message;

  /// The refused write's data as JSON, so a screen can offer to send it again.
  final String? payload;

  /// UTC ISO 8601.
  final String createdAt;

  /// `put`, `patch` or `delete`.
  final String? op;

  SyncRejection copyWith({String? message}) => SyncRejection(
        id: id,
        table: table,
        rowId: rowId,
        action: action,
        code: code,
        message: message ?? this.message,
        payload: payload,
        createdAt: createdAt,
        op: op,
      );
}

/// Read and clear access to the notes of a [SyncStore].
class Rejections {
  const Rejections(this.store);

  final SyncStore store;

  Future<List<SyncRejection>> all() => store.rejections();

  /// The notes for one row (for example "this row was not saved").
  Future<List<SyncRejection>> forRow(String table, String rowId) async => [
        for (final r in await store.rejections())
          if (r.table == table && r.rowId == rowId) r,
      ];

  Future<void> clear(String id) => store.clearRejection(id);

  Future<void> clearAll() async {
    for (final r in await store.rejections()) {
      await store.clearRejection(r.id);
    }
  }

  Stream<List<SyncRejection>> watch() => store.watchRejections();
}
