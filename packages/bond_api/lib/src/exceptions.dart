/// Typed failures from the API. Screens switch on the subtype.
library;

/// The base of every failure [ApiClient] throws.
///
/// The family is the superset of the consuming apps' exceptions: every field
/// any of them read is here, so call sites move over by renaming the import.
sealed class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  /// A 5xx or otherwise unusable server answer.
  factory ApiException.server(String message, {int? statusCode}) => ServerError(message, statusCode: statusCode);

  /// A 400: the request itself was wrong (not a field validation failure).
  factory ApiException.badRequest(String message) => BadRequest(message);

  final String message;
  final int? statusCode;

  @override
  String toString() => '$runtimeType($statusCode): $message';
}

/// The request never produced an HTTP answer.
class NetworkError extends ApiException {
  const NetworkError([super.message = 'Network error']);
}

/// A 401.
class Unauthorized extends ApiException {
  const Unauthorized([super.message = 'Unauthorized', this.code, this.refreshRejected = false])
      : super(statusCode: 401);

  /// The server's named reason when it gave one (`session_revoked`, `invalid_token`).
  final String? code;

  /// True when the client tried to renew the session and the server or the
  /// identity provider refused (not when it was merely offline).
  final bool refreshRejected;
}

/// A 403.
class Forbidden extends ApiException {
  const Forbidden([super.message = 'Forbidden', this.code, this.hint]) : super(statusCode: 403);

  /// The server's named reason when it gave one (`deactivated`, `not_invited`,
  /// `email_not_verified`, `identity_mismatch`).
  final String? code;

  /// A second named detail (`apple_relay` on `not_invited`: the e-mail is a
  /// private relay address).
  final String? hint;
}

/// A 404.
class NotFound extends ApiException {
  const NotFound([super.message = 'Not found', this.code, this.data = const {}]) : super(statusCode: 404);

  final String? code;

  /// The rest of the server's `detail` object.
  final Map<String, Object?> data;
}

/// A 409.
class Conflict extends ApiException {
  const Conflict(super.message, {this.code, this.data = const {}}) : super(statusCode: 409);

  final String? code;

  /// The rest of the server's `detail` object (a conflict can carry the row
  /// that is already there).
  final Map<String, Object?> data;
}

/// A 400.
class BadRequest extends ApiException {
  const BadRequest(super.message, [this.code]) : super(statusCode: 400);

  /// The server's named reason when the 400 detail carried one.
  final String? code;
}

/// A 422.
class ValidationError extends ApiException {
  const ValidationError(super.message, {this.fields = const {}, this.code, this.data = const {}})
      : super(statusCode: 422);

  /// Field name to message.
  final Map<String, String> fields;

  /// A named failure such as `validation_error`, when the detail is an object.
  final String? code;

  /// The rest of the server's `detail` object.
  final Map<String, Object?> data;
}

/// A 5xx, or any other status without its own class (405, 413, 429, ...).
class ServerError extends ApiException {
  const ServerError(super.message, {super.statusCode, this.code});

  /// The server's named reason (`db_unavailable`), when it gave one.
  final String? code;
}

/// A 2xx answer whose body is not the shape the caller expected (code
/// `bad_response`). The server handled the request; the client could not read
/// the answer. Not retryable on its own. [path] names the call.
class BadResponse extends ServerError {
  const BadResponse([this.path = '', String message = 'Unexpected response from the server'])
      : super(message, statusCode: 200, code: 'bad_response');

  final String path;

  @override
  String toString() => 'BadResponse(${path.isEmpty ? '' : '$path: '}$message)';
}

/// How a request failed before the app got a usable answer.
enum NetworkFailureKind {
  /// Nothing answered: connection refused, DNS, or a browser-side (CORS) block.
  noAnswer,

  /// The server did not answer, or did not finish answering, in time.
  timeout,

  /// The server answered 2xx but the body was not JSON (an HTML error page).
  badBody,

  /// The server answered with an error status (see [NetworkFailure.status]).
  http,
}

/// A request that failed on the way, carrying the failure [kind] and the
/// [baseUrl] it was sent to so a screen can say where. It is a [NetworkError],
/// so code that treats any network problem alike keeps working.
class NetworkFailure extends NetworkError {
  const NetworkFailure(this.kind, {required this.baseUrl, this.status, String? message, this.cause})
      : super(message ?? 'Network failure');

  final NetworkFailureKind kind;
  final String baseUrl;

  /// The HTTP status for [NetworkFailureKind.http] and [NetworkFailureKind.badBody].
  final int? status;

  /// The underlying error text, kept for logs.
  final String? cause;

  @override
  int? get statusCode => status;

  @override
  String toString() => 'NetworkFailure(${kind.name}, $baseUrl${status == null ? '' : ', $status'}): $message';
}

/// Reads any failure as a [NetworkFailure] when it is one a person can act on
/// by checking the connection or the server: no answer, too slow, an unreadable
/// body, or a 404 or 5xx status. Null for everything else (a 409, a 422 field
/// message, a sign-in refusal), which the screen words itself.
NetworkFailure? asNetworkFailure(Object error, {required String baseUrl}) {
  if (error is NetworkFailure) return error;
  if (error is BadResponse) {
    return NetworkFailure(NetworkFailureKind.badBody,
        baseUrl: baseUrl, status: error.statusCode, message: error.message);
  }
  if (error is NetworkError) {
    return NetworkFailure(NetworkFailureKind.noAnswer, baseUrl: baseUrl, message: error.message);
  }
  if (error is ApiException && (error is NotFound || (error.statusCode ?? 0) >= 500)) {
    return NetworkFailure(NetworkFailureKind.http,
        baseUrl: baseUrl, status: error.statusCode, message: error.message);
  }
  return null;
}

extension ApiExceptionDetail on ApiException {
  /// The server's own explanation, when it gave one a person can read (a 422
  /// field message, a 400 or 409 detail). Null for network and 5xx failures,
  /// where the screen shows its generic text.
  String? get userDetail {
    final e = this;
    if (e is ValidationError) {
      if (e.fields.isNotEmpty) return e.fields.values.where((v) => v.isNotEmpty).join(' ');
      return e.message == 'Validation failed' ? null : e.message;
    }
    if (e is BadRequest || e is Conflict) return e.message;
    return null;
  }
}
