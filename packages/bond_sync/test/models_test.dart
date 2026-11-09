import 'package:bond_json/bond_json.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:test/test.dart';

void main() {
  group('SyncToken', () {
    test('reads every field and keeps UTC', () {
      final t = SyncToken.fromJson({
        'token': 'abc.def.ghi',
        'expires_at': '2026-11-08T12:00:00Z',
        'endpoint': 'https://sync.example.com',
        'server_now': '2026-11-08T11:45:00.123Z',
      });
      expect(t.token, 'abc.def.ghi');
      expect(t.expiresAt, DateTime.utc(2026, 11, 8, 12));
      expect(t.expiresAt.isUtc, isTrue);
      expect(t.endpoint, 'https://sync.example.com');
      expect(t.serverNow, DateTime.utc(2026, 11, 8, 11, 45, 0, 123));
    });

    test('endpoint and server_now are optional', () {
      final t = SyncToken.fromJson({'token': 't', 'expires_at': '2026-11-08T12:00:00Z'});
      expect(t.endpoint, isNull);
      expect(t.serverNow, isNull);
      expect(t.toJson().containsKey('endpoint'), isFalse);
    });

    test('a missing token or expiry throws a shape error', () {
      expect(() => SyncToken.fromJson({'expires_at': '2026-11-08T12:00:00Z'}), throwsA(isA<JsonShapeError>()));
      expect(() => SyncToken.fromJson({'token': 't'}), throwsA(isA<JsonShapeError>()));
    });

    test('round trips through toJson', () {
      final j = {
        'token': 't',
        'expires_at': '2026-11-08T12:00:00.000Z',
        'endpoint': 'https://sync.example.com',
        'server_now': '2026-11-08T11:45:00.000Z',
      };
      expect(SyncToken.fromJson(SyncToken.fromJson(j).toJson()).toJson(), j);
    });
  });

  group('SyncUploadOp and UploadRequest', () {
    test('toJson omits a null action', () {
      const op = SyncUploadOp(seq: 0, op: 'put', table: 'notes', id: 'n1', data: {'title': 'x'});
      expect(op.toJson(), {
        'seq': 0,
        'op': 'put',
        'table': 'notes',
        'id': 'n1',
        'data': {'title': 'x'},
      });
    });

    test('toJson keeps an action', () {
      const op = SyncUploadOp(seq: 1, op: 'patch', table: 'tasks', id: 't', action: 'complete');
      expect(op.toJson()['action'], 'complete');
      expect(op.toJson()['data'], isEmpty);
    });

    test('a request omits a null transaction id and round trips', () {
      const op = SyncUploadOp(seq: 0, op: 'delete', table: 'notes', id: 'n1');
      expect(const UploadRequest(ops: [op]).toJson().containsKey('transaction_id'), isFalse);
      final r = UploadRequest.fromJson(const UploadRequest(transactionId: 7, ops: [op]).toJson());
      expect(r.transactionId, 7);
      expect(r.ops.single.id, 'n1');
      expect(r.ops.single.action, isNull);
    });

    test('an op that is not an object throws a shape error', () {
      expect(() => UploadRequest.fromJson({'ops': [1]}), throwsA(isA<JsonShapeError>()));
    });
  });

  group('UploadResponse', () {
    test('reads verdicts with absent keys', () {
      final r = UploadResponse.fromJson({
        'results': [
          {'seq': 0, 'status': 'ok'},
          {'seq': 1, 'status': 'ok', 'resolved_id': 'srv-1'},
          {'seq': 2, 'status': 'rejected', 'code': 'invalid', 'message': 'title is required'},
          {'seq': 3, 'status': 'skipped', 'code': 'already'},
        ],
        'server_now': '2026-11-08T11:45:00.000Z',
      });
      expect(r.results.map((e) => e.status), ['ok', 'ok', 'rejected', 'skipped']);
      expect(r.results[1].resolvedId, 'srv-1');
      expect(r.results[2].code, 'invalid');
      expect(r.results[0].code, isNull);
      expect(r.serverNow, DateTime.utc(2026, 11, 8, 11, 45));
    });

    test('an empty body reads as no results', () {
      final r = UploadResponse.fromJson({});
      expect(r.results, isEmpty);
      expect(r.serverNow, isNull);
    });

    test('toJson omits absent keys and round trips', () {
      final j = {
        'results': [
          {'seq': 0, 'status': 'ok'},
          {'seq': 1, 'status': 'rejected', 'code': 'forbidden', 'message': 'no'},
        ],
        'server_now': '2026-11-08T11:45:00.000Z',
      };
      expect(UploadResponse.fromJson(j).toJson(), j);
    });
  });
}
