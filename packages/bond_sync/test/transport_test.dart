import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_sync/bond_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

ApiClient _client(MockClient m) => ApiClient(baseUrl: Uri.parse('http://localhost:8012'), http: m);

http.Response _json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  test('upload posts the envelope to /sync/upload and reads the verdicts', () async {
    late http.Request seen;
    final api = _client(MockClient((r) async {
      seen = r;
      return _json({
        'results': [
          {'seq': 0, 'status': 'ok'},
        ],
        'server_now': '2026-11-08T10:00:00.000Z',
      });
    }));
    final t = ApiSyncTransport(api);
    final r = await t.upload(const UploadRequest(
      transactionId: 3,
      ops: [SyncUploadOp(seq: 0, op: 'put', table: 'notes', id: 'n1', data: {'title': 'a'})],
    ));
    expect(seen.method, 'POST');
    expect(seen.url.path, '/sync/upload');
    expect(jsonDecode(seen.body), {
      'transaction_id': 3,
      'ops': [
        {'seq': 0, 'op': 'put', 'table': 'notes', 'id': 'n1', 'data': {'title': 'a'}},
      ],
    });
    expect(r.results.single.status, 'ok');
    expect(r.serverNow, DateTime.utc(2026, 11, 8, 10));
  });

  test('fetchToken posts to /sync/token', () async {
    late http.Request seen;
    final api = _client(MockClient((r) async {
      seen = r;
      return _json({'token': 'tok', 'expires_at': '2026-11-08T10:15:00Z', 'endpoint': 'https://s', 'server_now': '2026-11-08T10:00:00Z'});
    }));
    final tok = await ApiSyncTransport(api).fetchToken();
    expect(seen.method, 'POST');
    expect(seen.url.path, '/sync/token');
    expect(tok.token, 'tok');
    expect(tok.endpoint, 'https://s');
  });

  test('the paths are the app\'s choice', () async {
    final seen = <String>[];
    final api = _client(MockClient((r) async {
      seen.add(r.url.path);
      return _json(r.url.path.endsWith('token')
          ? {'token': 't', 'expires_at': '2026-11-08T10:15:00Z'}
          : {'results': <Object>[]});
    }));
    final t = ApiSyncTransport(api, tokenPath: '/api/v1/ps/token', uploadPath: '/api/v1/ps/upload');
    await t.fetchToken();
    await t.upload(const UploadRequest(ops: []));
    expect(seen, ['/api/v1/ps/token', '/api/v1/ps/upload']);
  });

  test('refreshSession uses the renewal, then the client hook, else rejects', () async {
    final api = _client(MockClient((r) async => _json({})));
    expect(await ApiSyncTransport(api).refreshSession(), SessionRefresh.rejected);
    api.onUnauthorized = () async => SessionRefresh.offline;
    expect(await ApiSyncTransport(api).refreshSession(), SessionRefresh.offline);
    expect(await ApiSyncTransport(api, renewal: () async => SessionRefresh.renewed).refreshSession(), SessionRefresh.renewed);
  });

  test('a renewal that throws counts as rejected', () async {
    final api = _client(MockClient((r) async => _json({})));
    final t = ApiSyncTransport(api, renewal: () async => throw StateError('x'));
    expect(await t.refreshSession(), SessionRefresh.rejected);
  });

  test('real failures classify through mapSyncFailure', () async {
    Future<SyncFailure> classify(http.Response Function() answer) async {
      final api = _client(MockClient((r) async => answer()));
      try {
        await ApiSyncTransport(api).upload(const UploadRequest(ops: []));
      } catch (e) {
        return mapSyncFailure(e);
      }
      fail('expected a failure');
    }

    expect(await classify(() => _json({'detail': 'down'}, 503)), SyncFailure.transientNoCount);
    expect(await classify(() => _json({'detail': 'no'}, 403)), SyncFailure.transientCounted);
    expect(await classify(() => _json({'detail': 'big'}, 413)), SyncFailure.permanent);
    expect(await classify(() => _json({'detail': 'bad'}, 422)), SyncFailure.permanent);
    expect(await classify(() => http.Response('<html>', 200)), SyncFailure.transientCounted);
  });
}
