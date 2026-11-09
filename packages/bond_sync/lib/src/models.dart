/// Wire shapes of the sync routes: token and upload (see docs/contracts/sync_upload.md).
library;

import 'package:bond_json/bond_json.dart';

Map<Object?, Object?> _asMap(Object? v, String path) {
  if (v is Map) return v;
  throw JsonShapeError(path, 'Map', describeJsonType(v));
}

T _required<T>(T? v, String key, String expected) {
  if (v == null) throw JsonShapeError(key, expected, 'null');
  return v;
}

/// The answer of `POST /sync/token`.
class SyncToken {
  const SyncToken({
    required this.token,
    required this.expiresAt,
    this.endpoint,
    this.serverNow,
  });

  factory SyncToken.fromJson(Map<Object?, Object?> j) => SyncToken(
        token: _required(jstr(j, 'token'), 'token', 'String'),
        expiresAt: _required(jtime(j, 'expires_at'), 'expires_at', 'ISO-8601 String'),
        endpoint: jstr(j, 'endpoint'),
        serverNow: jtime(j, 'server_now'),
      );

  final String token;

  /// UTC.
  final DateTime expiresAt;

  /// The sync service URL the server hands out; null when it did not say.
  final String? endpoint;
  final DateTime? serverNow;

  Map<String, Object?> toJson() => {
        'token': token,
        'expires_at': jiso(expiresAt),
        if (endpoint != null) 'endpoint': endpoint,
        if (serverNow != null) 'server_now': jiso(serverNow!),
      };
}

/// One queued write as `POST /sync/upload` takes it.
class SyncUploadOp {
  const SyncUploadOp({
    required this.seq,
    required this.op,
    required this.table,
    required this.id,
    this.action,
    this.data = const {},
  });

  factory SyncUploadOp.fromJson(Map<Object?, Object?> j) => SyncUploadOp(
        seq: _required(jint(j, 'seq'), 'seq', 'int'),
        op: _required(jstr(j, 'op'), 'op', 'String'),
        table: _required(jstr(j, 'table'), 'table', 'String'),
        id: _required(jstr(j, 'id'), 'id', 'String'),
        action: jstr(j, 'action'),
        data: jmap(j, 'data') ?? const {},
      );

  final int seq;

  /// `put`, `patch` or `delete`.
  final String op;
  final String table;
  final String id;
  final String? action;
  final Map<String, Object?> data;

  /// `action` is omitted when null.
  Map<String, Object?> toJson() => {
        'seq': seq,
        'op': op,
        'table': table,
        'id': id,
        if (action != null) 'action': action,
        'data': data,
      };
}

class UploadRequest {
  const UploadRequest({this.transactionId, required this.ops});

  factory UploadRequest.fromJson(Map<Object?, Object?> j) => UploadRequest(
        transactionId: jint(j, 'transaction_id'),
        ops: jlist(j, 'ops', (o) => SyncUploadOp.fromJson(_asMap(o, 'ops'))),
      );

  final int? transactionId;
  final List<SyncUploadOp> ops;

  Map<String, Object?> toJson() => {
        if (transactionId != null) 'transaction_id': transactionId,
        'ops': [for (final o in ops) o.toJson()],
      };
}

/// The server's answer for one op: `ok`, `rejected` or `skipped`.
class SyncOpResult {
  const SyncOpResult({
    required this.seq,
    required this.status,
    this.code,
    this.message,
    this.resolvedId,
  });

  factory SyncOpResult.fromJson(Map<Object?, Object?> j) => SyncOpResult(
        seq: _required(jint(j, 'seq'), 'seq', 'int'),
        status: _required(jstr(j, 'status'), 'status', 'String'),
        code: jstr(j, 'code'),
        message: jstr(j, 'message'),
        resolvedId: jstr(j, 'resolved_id'),
      );

  final int seq;
  final String status;
  final String? code;
  final String? message;

  /// Set on `ok` when the server chose another primary key than the device.
  final String? resolvedId;

  /// Absent keys are omitted.
  Map<String, Object?> toJson() => {
        'seq': seq,
        'status': status,
        if (code != null) 'code': code,
        if (message != null) 'message': message,
        if (resolvedId != null) 'resolved_id': resolvedId,
      };
}

class UploadResponse {
  const UploadResponse({required this.results, this.serverNow});

  factory UploadResponse.fromJson(Map<Object?, Object?> j) => UploadResponse(
        results: jlist(j, 'results', (o) => SyncOpResult.fromJson(_asMap(o, 'results'))),
        serverNow: jtime(j, 'server_now'),
      );

  final List<SyncOpResult> results;
  final DateTime? serverNow;

  Map<String, Object?> toJson() => {
        'results': [for (final r in results) r.toJson()],
        if (serverNow != null) 'server_now': jiso(serverNow!),
      };
}
