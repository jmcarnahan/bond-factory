/// How a failed request is classified for the uploader.
library;

import 'package:bond_api/bond_api.dart';

/// The failure classes the uploader understands. An app maps its own
/// exceptions to these with a [FailureMapper].
enum SyncFailure {
  /// No network, or no answer in time. Retried, never counted.
  offline,

  /// The session is not accepted (401). Renewed once, else retried.
  unauthorized,

  /// The whole chunk is refused (409, 410, 413, 422, other 4xx).
  permanent,

  /// An edge or outage answer that says nothing about the data: retried, never counted.
  transientNoCount,

  /// The server's trouble that may be about this data (403, 408, an unreadable
  /// body): retried and counted toward giving the transaction up.
  transientCounted,
}

typedef FailureMapper = SyncFailure Function(Object error);

/// The default mapping over `bond_api` exceptions.
///
/// - [NetworkError] (no answer, timeout): offline. A [NetworkFailure] whose
///   body was unreadable: transientCounted; one that failed on an HTTP status:
///   transientNoCount.
/// - [Unauthorized]: unauthorized.
/// - [Conflict] 409, [ValidationError] 422, status 410 and 413: permanent.
/// - 5xx: transientNoCount. The upload route answers 5xx only when its
///   database is unreachable; an op-level bug is a per-op `server_error`
///   verdict inside a 200. (The seed's core comment said "counted" while its
///   mapper said "not counted"; the mapper wins.)
/// - [Forbidden] 403, 408 and an unreadable 2xx body ([BadResponse]): transientCounted.
/// - 400, 404, 405, 429: edge answers, not a verdict on the data: transientNoCount.
/// - Any other 4xx: permanent. Anything unknown: transientCounted.
SyncFailure mapSyncFailure(Object error) {
  if (error is NetworkFailure) {
    return switch (error.kind) {
      NetworkFailureKind.badBody => SyncFailure.transientCounted,
      NetworkFailureKind.http => SyncFailure.transientNoCount,
      _ => SyncFailure.offline,
    };
  }
  if (error is NetworkError) return SyncFailure.offline;
  if (error is Unauthorized) return SyncFailure.unauthorized;
  if (error is Conflict || error is ValidationError) return SyncFailure.permanent;
  if (error is Forbidden || error is BadResponse) return SyncFailure.transientCounted;
  if (error is NotFound || error is BadRequest) return SyncFailure.transientNoCount;
  if (error is ServerError) {
    final code = error.statusCode;
    if (code == null) return SyncFailure.transientCounted;
    if (code >= 500) return SyncFailure.transientNoCount;
    if (code == 410 || code == 413) return SyncFailure.permanent;
    if (code == 405 || code == 429) return SyncFailure.transientNoCount;
    if (code == 408) return SyncFailure.transientCounted;
    if (code >= 400) return SyncFailure.permanent;
    return SyncFailure.transientCounted; // an unexpected 2xx/3xx
  }
  return SyncFailure.transientCounted;
}
