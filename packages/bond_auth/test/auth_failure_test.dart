import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:test/test.dart';

void main() {
  group('AuthFailure.fromApi', () {
    final cases = <String, (ApiException, AuthFailureReason, String?)>{
      'not_invited': (const Forbidden('x', 'not_invited'), AuthFailureReason.notInvited, 'not_invited'),
      'apple relay': (const Forbidden('x', 'not_invited', 'apple_relay'), AuthFailureReason.appleRelay, 'not_invited'),
      'deactivated': (const Forbidden('x', 'deactivated'), AuthFailureReason.disabled, 'deactivated'),
      'identity_mismatch': (const Forbidden('x', 'identity_mismatch'), AuthFailureReason.other, 'identity_mismatch'),
      'email_not_verified': (const Forbidden('x', 'email_not_verified'), AuthFailureReason.other, 'email_not_verified'),
      'invalid_token': (const Unauthorized('x', 'invalid_token'), AuthFailureReason.wrongCredentials, 'invalid_token'),
      'bare 401': (const Unauthorized('x'), AuthFailureReason.wrongCredentials, null),
      'session_revoked': (const Unauthorized('x', 'session_revoked'), AuthFailureReason.other, 'session_revoked'),
      '429': (const ServerError('slow down', statusCode: 429), AuthFailureReason.rateLimited, 'rate_limited'),
      'network': (
        const NetworkFailure(NetworkFailureKind.noAnswer, baseUrl: 'http://h'),
        AuthFailureReason.network,
        null,
      ),
      'provider_not_allowed': (const Forbidden('x', 'provider_not_allowed'), AuthFailureReason.other, 'provider_not_allowed'),
      'company_suspended': (const Forbidden('x', 'company_suspended'), AuthFailureReason.other, 'company_suspended'),
      '501 firebase_not_configured': (
        const ServerError('x', statusCode: 501, code: 'firebase_not_configured'),
        AuthFailureReason.notConfigured,
        'firebase_not_configured',
      ),
      'demo off (404)': (const NotFound('Not found', 'not_found'), AuthFailureReason.notConfigured, 'not_found'),
      '503 auth_unavailable': (
        const ServerError('x', statusCode: 503, code: 'auth_unavailable'),
        AuthFailureReason.network,
        'auth_unavailable',
      ),
      '503 db_unavailable': (
        const ServerError('x', statusCode: 503, code: 'db_unavailable'),
        AuthFailureReason.network,
        'db_unavailable',
      ),
      '409 keeps its code': (const Conflict('x', code: 'id_taken'), AuthFailureReason.other, 'id_taken'),
      '400 keeps its code': (const BadRequest('x', 'bad_request'), AuthFailureReason.other, 'bad_request'),
      '422 keeps its code': (const ValidationError('x', code: 'validation_error'), AuthFailureReason.other, 'validation_error'),
      '500': (const ServerError('boom', statusCode: 500, code: 'internal_error'), AuthFailureReason.other, 'internal_error'),
    };
    cases.forEach((name, c) {
      test(name, () {
        final f = AuthFailure.fromApi(c.$1);
        expect(f.reason, c.$2);
        expect(f.code, c.$3);
      });
    });

    test('keeps the message', () {
      expect(AuthFailure.fromApi(const Forbidden('Not on the list', 'not_invited')).message, 'Not on the list');
    });
  });
}
