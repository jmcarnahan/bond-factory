import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:test/test.dart';

void main() {
  group('dict detail', () {
    for (final (status, type) in <(int, Matcher)>[
      (400, isA<BadRequest>()),
      (401, isA<Unauthorized>()),
      (403, isA<Forbidden>()),
      (404, isA<NotFound>()),
      (409, isA<Conflict>()),
      (422, isA<ValidationError>()),
      (500, isA<ServerError>()),
      (503, isA<ServerError>()),
    ]) {
      test('$status maps to its class with code and message', () {
        final e = ErrorBody.parse(status, {
          'detail': {'code': 'some_code', 'message': 'Words.', 'extra': 1},
        });
        expect(e, type);
        expect(e.message, 'Words.');
        expect(e.statusCode, status);
        expect(switch (e) {
          Unauthorized(:final code) => code,
          Forbidden(:final code) => code,
          NotFound(:final code) => code,
          Conflict(:final code) => code,
          BadRequest(:final code) => code,
          ValidationError(:final code) => code,
          ServerError(:final code) => code,
          _ => null,
        }, 'some_code');
      });
    }

    test('403 hint is read from the detail', () {
      final e = ErrorBody.parse(403, {
        'detail': {'code': 'not_invited', 'message': 'No.', 'hint': 'apple_relay'},
      });
      expect(e, isA<Forbidden>().having((f) => f.hint, 'hint', 'apple_relay'));
    });

    test('data keeps the whole detail', () {
      final e = ErrorBody.parse(409, {
        'detail': {'code': 'open_entry', 'message': 'm', 'entry': {'id': 'x'}},
      }) as Conflict;
      expect(e.data['entry'], {'id': 'x'});
    });

    test('message falls back to detail.detail then the status', () {
      expect(ErrorBody.parse(409, {'detail': {'detail': 'inner'}}).message, 'inner');
      expect(ErrorBody.parse(409, {'detail': <String, Object?>{}}).message, 'HTTP 409');
    });

    test('validation_error carries the errors list as fields', () {
      final e = ErrorBody.parse(422, {
        'detail': {
          'code': 'validation_error',
          'message': 'name: required',
          'errors': [
            {'loc': ['body', 'name'], 'msg': 'required', 'type': 'missing'},
          ],
        },
      }) as ValidationError;
      expect(e.code, 'validation_error');
      expect(e.fields, {'name': 'required'});
      expect(e.message, 'name: required');
    });
  });

  group('string detail', () {
    test('401 and 403 take the string as code too', () {
      final u = ErrorBody.parse(401, {'detail': 'session_revoked'}) as Unauthorized;
      expect(u.code, 'session_revoked');
      expect(u.message, 'session_revoked');
      final f = ErrorBody.parse(403, {'detail': 'deactivated'}) as Forbidden;
      expect(f.code, 'deactivated');
    });

    test('other statuses keep it as the message only', () {
      final e = ErrorBody.parse(404, {'detail': 'Customer not found'}) as NotFound;
      expect(e.message, 'Customer not found');
      expect(e.code, isNull);
      final c = ErrorBody.parse(409, {'detail': 'Taken'}) as Conflict;
      expect(c.code, isNull);
      expect(c.message, 'Taken');
    });
  });

  group('list detail', () {
    test('422 builds field errors from the last loc part', () {
      final e = ErrorBody.parse(422, {
        'detail': [
          {'loc': ['body', 'email'], 'msg': 'bad email'},
          {'loc': ['query', 'n'], 'msg': 'too big'},
        ],
      }) as ValidationError;
      expect(e.fields, {'email': 'bad email', 'n': 'too big'});
      expect(e.message, 'Validation failed');
      expect(e.userDetail, 'bad email too big');
    });
  });

  group('error code keys', () {
    String? codeOf(Object body) => ErrorBody.from(409, body).code;

    test('each key alone, in the detail map and at the top level', () {
      for (final key in ['code', 'error_code', 'error']) {
        expect(codeOf({'detail': {key: 'slot_taken', 'message': 'm'}}), 'slot_taken', reason: 'detail $key');
        expect(codeOf({key: 'slot_taken', 'detail': 'x'}), 'slot_taken', reason: 'top $key');
      }
    });

    test('precedence is code, then error_code, then error', () {
      expect(codeOf({'detail': {'error': 'c', 'error_code': 'b', 'code': 'a'}}), 'a');
      expect(codeOf({'detail': {'error': 'c', 'error_code': 'b'}}), 'b');
      expect(codeOf({'error': 'c', 'error_code': 'b', 'code': 'a', 'detail': 'x'}), 'a');
      expect(codeOf({'error': 'c', 'error_code': 'b', 'detail': 'x'}), 'b');
    });

    test('the detail map wins over the top level', () {
      expect(codeOf({'code': 'top', 'detail': {'error': 'inner'}}), 'inner');
    });

    test('a human sentence in error is not the code and never replaces the message', () {
      final e = ErrorBody.from(409, {'detail': {'error': 'Slot is already taken', 'message': 'Taken'}});
      expect(e.code, isNull);
      expect(e.message, 'Taken');
      expect(ErrorBody.from(409, {'error': 'Not a code!', 'detail': 'x'}).code, isNull);
      expect(codeOf({'detail': {'error': 'a' * 65}}), isNull);
      expect(codeOf({'detail': {'error': 'a' * 64}}), 'a' * 64);
      expect(codeOf({'detail': {'error': 'Upper'}}), isNull);
    });

    test('a sentence in error does not hide a real code, and error is not the message', () {
      final e = ErrorBody.from(409, {'detail': {'error': 'Some sentence', 'error_code': 'taken'}});
      expect(e.code, 'taken');
      expect(e.message, 'HTTP 409');
    });

    test('non-string values are ignored', () {
      expect(codeOf({'detail': {'code': 42, 'error_code': 'b'}}), 'b');
      expect(codeOf({'detail': {'code': 42, 'error_code': 7, 'error': true}}), isNull);
      expect(codeOf({'code': 5, 'error': 'real_code', 'detail': 'x'}), 'real_code');
    });

    test('an empty or blank code does not beat a valid error_code or error', () {
      expect(codeOf({'detail': {'code': '', 'error_code': 'b'}}), 'b');
      expect(codeOf({'detail': {'code': '  ', 'error_code': '', 'error': 'c_d'}}), 'c_d');
      expect(codeOf({'code': '', 'error': 'c_d', 'detail': 'x'}), 'c_d');
      expect(codeOf({'detail': {'code': '', 'error_code': ''}}), isNull);
    });

    test('the legacy string detail is unchanged', () {
      final e = ErrorBody.from(401, {'detail': 'invalid_token'});
      expect(e.code, 'invalid_token');
      expect(e.message, 'invalid_token');
      expect(ErrorBody.from(409, {'detail': 'taken'}).code, isNull);
      expect(ErrorBody.from(409, {'detail': 'taken', 'error': 'x_y'}).code, 'x_y');
    });
  });

  group('shapes', () {
    test('top-level code is the fallback', () {
      final e = ErrorBody.parse(500, {'code': 'db_unavailable', 'detail': 'x'}) as ServerError;
      expect(e.code, 'db_unavailable');
      expect(e.statusCode, 500);
    });

    test('raw JSON text is decoded', () {
      final e = ErrorBody.parse(403, jsonEncode({'detail': {'code': 'deactivated', 'message': 'Off.'}}));
      expect(e, isA<Forbidden>().having((f) => f.code, 'code', 'deactivated'));
    });

    test('non-JSON text becomes the message', () {
      final e = ErrorBody.parse(502, '<html>Bad gateway</html>');
      expect(e, isA<ServerError>());
      expect(e.message, 'HTTP 502: <html>Bad gateway</html>');
    });

    test('a long multi-line non-JSON body is one line of at most 200 characters after the status', () {
      final page = '<html>\n  <body>\r\n${'x' * 500}\n</body></html>';
      final e = ErrorBody.parse(503, page);
      expect(e.message, startsWith('HTTP 503: <html> <body> xxx'));
      expect(e.message, isNot(contains('\n')));
      expect(e.message, isNot(contains('\r')));
      expect(e.message.length, 'HTTP 503: '.length + 200);
    });

    test('a JSON body with no detail is trimmed the same way', () {
      final e = ErrorBody.parse(500, '{"blob":"${'y' * 400}"}');
      expect(e.message.length, lessThanOrEqualTo('HTTP 500: '.length + 200));
    });

    test('empty and null bodies answer by status', () {
      expect(ErrorBody.parse(404, '').message, 'HTTP 404');
      expect(ErrorBody.parse(500, null).message, 'HTTP 500');
    });

    test('a list body or odd types never throw', () {
      expect(ErrorBody.parse(500, [1, 2]), isA<ServerError>());
      expect(ErrorBody.parse(403, {'detail': {'code': 5, 'message': 7, 'hint': 3}}), isA<Forbidden>());
    });

    test('other statuses are server errors carrying the status', () {
      for (final s in [405, 413, 429, 501]) {
        expect(ErrorBody.parse(s, null), isA<ServerError>().having((e) => e.statusCode, 'status', s));
      }
    });
  });
}
