import 'package:bond_api/bond_api.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:test/test.dart';

NetworkFailure _net(NetworkFailureKind k) => NetworkFailure(k, baseUrl: 'http://x');

void main() {
  group('mapSyncFailure', () {
    test('network problems are offline', () {
      expect(mapSyncFailure(_net(NetworkFailureKind.noAnswer)), SyncFailure.offline);
      expect(mapSyncFailure(_net(NetworkFailureKind.timeout)), SyncFailure.offline);
      expect(mapSyncFailure(const NetworkError()), SyncFailure.offline);
    });

    test('an unreadable body counts, an http status does not', () {
      expect(mapSyncFailure(_net(NetworkFailureKind.badBody)), SyncFailure.transientCounted);
      expect(mapSyncFailure(_net(NetworkFailureKind.http)), SyncFailure.transientNoCount);
      expect(mapSyncFailure(const BadResponse('/sync/upload')), SyncFailure.transientCounted);
    });

    test('401 is unauthorized', () {
      expect(mapSyncFailure(const Unauthorized()), SyncFailure.unauthorized);
    });

    test('5xx is the decided contradiction: transientNoCount', () {
      for (final s in [500, 502, 503, 504]) {
        expect(mapSyncFailure(ServerError('x', statusCode: s)), SyncFailure.transientNoCount, reason: '$s');
      }
    });

    test('403, 408 and no status count', () {
      expect(mapSyncFailure(const Forbidden()), SyncFailure.transientCounted);
      expect(mapSyncFailure(const ServerError('x', statusCode: 408)), SyncFailure.transientCounted);
      expect(mapSyncFailure(const ServerError('x')), SyncFailure.transientCounted);
    });

    test('409, 410, 413, 422 refuse the chunk', () {
      expect(mapSyncFailure(const Conflict('x')), SyncFailure.permanent);
      expect(mapSyncFailure(const ValidationError('x')), SyncFailure.permanent);
      expect(mapSyncFailure(const ServerError('x', statusCode: 410)), SyncFailure.permanent);
      expect(mapSyncFailure(const ServerError('x', statusCode: 413)), SyncFailure.permanent);
    });

    test('400, 404, 405, 429 are edge answers, not a verdict', () {
      expect(mapSyncFailure(const BadRequest('x')), SyncFailure.transientNoCount);
      expect(mapSyncFailure(const NotFound()), SyncFailure.transientNoCount);
      expect(mapSyncFailure(const ServerError('x', statusCode: 405)), SyncFailure.transientNoCount);
      expect(mapSyncFailure(const ServerError('x', statusCode: 429)), SyncFailure.transientNoCount);
    });

    test('another 4xx is permanent and an unknown error counts', () {
      expect(mapSyncFailure(const ServerError('x', statusCode: 418)), SyncFailure.permanent);
      expect(mapSyncFailure(StateError('boom')), SyncFailure.transientCounted);
    });
  });
}
