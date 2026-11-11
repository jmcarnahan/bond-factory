import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:roof_demo/src/service_client.dart';

ServiceClient _client(http.Response Function(http.Request) h, {String token = 'tok'}) => ServiceClient(
      baseUrl: 'http://test',
      token: token,
      pollInterval: Duration.zero,
      client: MockClient((r) async => h(r)),
    );

void main() {
  test('fixtures() reads the service object list as stems', () async {
    final c = _client((_) => http.Response(
        '[{"name":"synthetic_gable","file":"synthetic_gable.json","bytes":10},'
        '{"name":"synthetic_hip","file":"synthetic_hip.json","bytes":20}]',
        200));
    expect(await c.fixtures(), ['synthetic_gable', 'synthetic_hip']);
  });

  test('fixtures() tolerates a plain string list and strips .json', () async {
    final c = _client((_) => http.Response('["a.json","b"]', 200));
    expect(await c.fixtures(), ['a', 'b']);
  });

  test('fixtures() returns empty on garbage', () async {
    for (final body in ['not json', '{"x":1}', '[1,2]', '[{"file":"x.json"}]', '[{"name":3}]']) {
      final c = _client((_) => http.Response(body, 200));
      expect(await c.fixtures(), isEmpty, reason: body);
    }
    expect(await _client((_) => http.Response('[]', 500)).fixtures(), isEmpty);
  });

  test('fixtureJson requests the stem', () async {
    Uri? seen;
    final c = _client((r) {
      seen = r.url;
      return http.Response('{"a":1}', 200);
    });
    await c.fixtureJson('x.json');
    expect(seen.toString(), 'http://test/fixtures/x');
  });

  group('job flow', () {
    test('POST /v1/measurements with bearer token and body, then polls until done', () async {
      final seen = <http.Request>[];
      var polls = 0;
      final c = _client((r) {
        seen.add(r);
        if (r.method == 'POST') return http.Response('{"id":"j1","status":"queued"}', 202);
        polls++;
        return http.Response(
            polls < 3 ? '{"id":"j1","status":"running"}' : '{"id":"j1","status":"done","result":{"contract":"bond.roof_model/0.2"}}',
            200);
      });
      final statuses = <String>[];
      final result = await c.measure('100 Example Ave', MeasureMethod.auto, onStatus: statuses.add);
      expect(result['contract'], 'bond.roof_model/0.2');
      expect(seen.first.url.toString(), 'http://test/v1/measurements');
      expect(seen.first.headers['authorization'], 'Bearer tok');
      expect(jsonDecode(seen.first.body), {'address': '100 Example Ave', 'method': 'auto', 'verify': true});
      expect(seen[1].url.toString(), 'http://test/v1/measurements/j1');
      expect(polls, 3);
      expect(statuses.first, 'Submitting...');
      expect(statuses.where((s) => s.startsWith('Job running')), hasLength(2));
    });

    test('a failed job throws code: message', () async {
      final c = _client((r) => r.method == 'POST'
          ? http.Response('{"id":"j2","status":"queued"}', 202)
          : http.Response(
              '{"id":"j2","status":"failed","error":{"code":"no_lidar_coverage","message":"No LiDAR here.","retryable":false}}', 200));
      await expectLater(
        c.measure('x', MeasureMethod.lidar),
        throwsA(isA<ServiceFailure>().having((e) => '$e', 'text', 'no_lidar_coverage: No LiDAR here.')),
      );
    });

    test('an HTTP error answer carries the service error object', () async {
      final c = _client((_) => http.Response('{"error":{"code":"unauthorized","message":"Bad token."}}', 401));
      await expectLater(c.measure('x', MeasureMethod.auto),
          throwsA(isA<ServiceFailure>().having((e) => e.code, 'code', 'unauthorized')));
    });

    test('gives up after the job timeout', () async {
      final c = ServiceClient(
        baseUrl: 'http://test',
        token: 't',
        pollInterval: const Duration(milliseconds: 5),
        jobTimeout: const Duration(milliseconds: 30),
        client: MockClient((r) async => r.method == 'POST'
            ? http.Response('{"id":"j3","status":"queued"}', 202)
            : http.Response('{"id":"j3","status":"running"}', 200)),
      );
      await expectLater(c.measure('x', MeasureMethod.auto),
          throwsA(isA<ServiceFailure>().having((e) => e.code, 'code', 'timeout')));
    });

    test('no token means no authorization header', () async {
      http.Request? seen;
      final c = _client((r) {
        seen = r;
        return http.Response('{"id":"j","status":"queued"}', 202);
      }, token: '');
      await c.submit('x', MeasureMethod.auto, verify: false);
      expect(seen!.headers.containsKey('authorization'), isFalse);
      expect(jsonDecode(seen!.body)['verify'], false);
    });

    test('a transient poll failure is retried, a permanent one is not', () async {
      var polls = 0;
      final c = _client((r) {
        if (r.method == 'POST') return http.Response('{"id":"j4","status":"queued"}', 202);
        polls++;
        if (polls == 1) return http.Response('{"error":{"code":"queue_full","message":"busy","retryable":true}}', 429);
        if (polls == 2) return http.Response('oops', 503);
        return http.Response('{"id":"j4","status":"done","result":{"a":1}}', 200);
      });
      expect(await c.measure('x', MeasureMethod.auto), {'a': 1});
      expect(polls, 3);

      var calls = 0;
      final bad = _client((r) {
        if (r.method == 'POST') return http.Response('{"id":"j5","status":"queued"}', 202);
        calls++;
        return http.Response('{"error":{"code":"unknown_job","message":"gone"}}', 404);
      });
      await expectLater(bad.measure('x', MeasureMethod.auto),
          throwsA(isA<ServiceFailure>().having((e) => e.code, 'code', 'unknown_job')));
      expect(calls, 1);
    });

    test('gives up after three retries of a failing poll', () async {
      var polls = 0;
      final c = _client((r) {
        if (r.method == 'POST') return http.Response('{"id":"j6","status":"queued"}', 202);
        polls++;
        return http.Response('down', 503);
      });
      await expectLater(c.measure('x', MeasureMethod.auto), throwsA(isA<ServiceFailure>()));
      expect(polls, 4);
    });

    test('a network error on poll is retried', () async {
      var polls = 0;
      final c = ServiceClient(
        baseUrl: 'http://test',
        token: 't',
        pollInterval: Duration.zero,
        client: MockClient((r) async {
          if (r.method == 'POST') return http.Response('{"id":"j7","status":"queued"}', 202);
          if (++polls == 1) throw http.ClientException('socket closed');
          return http.Response('{"id":"j7","status":"done","result":{"b":2}}', 200);
        }),
      );
      expect(await c.measure('x', MeasureMethod.auto), {'b': 2});
    });

    test('a submit answer without an id fails inline instead of polling null', () async {
      var polled = false;
      final c = _client((r) {
        if (r.method != 'POST') polled = true;
        return http.Response('{"status":"queued"}', 202);
      });
      await expectLater(c.measure('x', MeasureMethod.auto),
          throwsA(isA<ServiceFailure>().having((e) => e.code, 'code', 'invalid_response')));
      expect(polled, isFalse);
    });
  });
}
