/// Reads an error response body into the right [ApiException].
library;

import 'dart:convert';

import 'exceptions.dart';

/// The parts of an error body that matter, and the exception they make.
///
/// The server speaks `{"detail": {"code", "message", ...}}` (a dict detail), but
/// older routes answer `{"detail": "some_code"}` (a string) and FastAPI's own
/// validation answers `{"detail": [{"loc": [...], "msg": "..."}]}` (a list).
/// All three, and a top-level code, are read here. The code key is `code`,
/// `error_code` or `error` (see [_readCode]).
class ErrorBody {
  const ErrorBody({
    required this.status,
    required this.message,
    this.code,
    this.data = const {},
    this.fields = const {},
  });

  /// Reads [body]: a decoded JSON value, or the raw response text (which is
  /// decoded when it is JSON and kept as the message when it is not).
  factory ErrorBody.from(int status, Object? body) {
    Object? decoded = body;
    var message = 'HTTP $status';
    if (body is String) {
      message = _snippet(status, body);
      try {
        decoded = body.isEmpty ? null : jsonDecode(body);
      } on FormatException {
        decoded = null;
      }
    }
    String? code;
    var data = const <String, Object?>{};
    final fields = <String, String>{};
    if (decoded is Map) {
      final detail = decoded['detail'];
      if (detail is String) {
        message = detail;
        // The sign-in routes answer with a bare reason: `not_invited`, `invalid_token`.
        // A top-level `code` / `error_code` beats the detail text.
        if (status == 401 || status == 403) code = _readExplicit(decoded) ?? detail;
      } else if (detail is Map) {
        message = (detail['message'] ?? detail['detail'] ?? message).toString();
        code = _readCode(detail);
        data = _stringKeyed(detail);
        _readFields(detail['errors'], fields);
      } else if (detail is List) {
        _readFields(detail, fields);
        message = 'Validation failed';
      }
      code ??= _readCode(decoded);
      if (data.isEmpty && detail is! List) data = _stringKeyed(decoded);
    }
    return ErrorBody(status: status, message: message, code: code, data: data, fields: fields);
  }

  static final _codeShape = RegExp(r'^[a-z][a-z0-9_]*$');

  /// The error code of [map]: `code`, then `error_code`, then `error`. Only a
  /// string counts. `error` is taken only when it looks like a code (servers
  /// also put human sentences there); it never touches the message.
  static String? _readExplicit(Map<dynamic, dynamic> map) {
    for (final key in const ['code', 'error_code']) {
      final v = map[key];
      if (v is String && v.trim().isNotEmpty) return v;
    }
    return null;
  }

  static String? _readCode(Map<dynamic, dynamic> map) {
    final explicit = _readExplicit(map);
    if (explicit != null) return explicit;
    final e = map['error'];
    return e is String && e.length <= 64 && _codeShape.hasMatch(e) ? e : null;
  }

  /// [ErrorBody.from] then [toException]. Never throws: a body of an unexpected
  /// shape (a numeric code, a string hint) is answered by status alone.
  static ApiException parse(int status, Object? body) {
    try {
      return ErrorBody.from(status, body).toException();
    } catch (_) {
      return ErrorBody(status: status, message: 'HTTP $status').toException();
    }
  }

  final int status;
  final String message;
  final String? code;
  final Map<String, Object?> data;
  final Map<String, String> fields;

  String? get hint {
    final h = data['hint'];
    return h is String ? h : null;
  }

  ApiException toException() => switch (status) {
        401 => Unauthorized(message, code),
        403 => Forbidden(message, code, hint),
        404 => NotFound(message, code, data),
        409 => Conflict(message, code: code, data: data),
        400 => BadRequest(message, code),
        422 => ValidationError(message, fields: fields, code: code, data: data),
        _ => ServerError(message, statusCode: status, code: code),
      };
}

/// `HTTP status` plus at most 200 characters of [body] on one line, so a proxy's
/// HTML page never becomes the whole message.
String _snippet(int status, String body) {
  final text = body.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (text.isEmpty) return 'HTTP $status';
  return 'HTTP $status: ${text.length > 200 ? text.substring(0, 200) : text}';
}

Map<String, Object?> _stringKeyed(Map<Object?, Object?> m) => {
      for (final e in m.entries) e.key.toString(): e.value,
    };

// Field errors: `[{loc: [body, name], msg}]`, the last `loc` part names the field.
void _readFields(Object? list, Map<String, String> into) {
  if (list is! List) return;
  for (final item in list) {
    if (item is! Map) continue;
    final loc = item['loc'];
    final name = loc is List && loc.isNotEmpty ? loc.last.toString() : '';
    into[name] = (item['msg'] ?? '').toString();
  }
}
