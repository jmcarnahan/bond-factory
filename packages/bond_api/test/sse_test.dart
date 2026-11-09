import 'dart:async';
import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

ApiClient _client(
  Stream<List<int>> Function(http.BaseRequest) body, {
  int status = 200,
  TokenSource? tokens,
  Future<SessionRefresh> Function()? onUnauthorized,
  List<http.BaseRequest>? seen,
}) =>
    ApiClient(
      baseUrl: Uri.parse('https://api.test/api/v1'),
      tokens: tokens,
      onUnauthorized: onUnauthorized,
      http: MockClient.streaming((req, _) async {
        seen?.add(req);
        return http.StreamedResponse(body(req), status, request: req);
      }),
    );

Stream<List<int>> _chunks(List<String> parts) => Stream.fromIterable(parts.map(utf8.encode));

void main() {
  group('SseFrameSplitter and parseSseFrame', () {
    test('splits frames across chunks, CRLF included', () {
      final s = SseFrameSplitter();
      expect(s.add('data: a\r'), isEmpty);
      expect(s.add('\n\r\ndata: b\n'), ['data: a']);
      expect(s.add('\ndata: c\n\n'), ['data: b', 'data: c']);
      expect(s.add('data: half'), isEmpty);
      expect(s.finish(), isEmpty);
    });

    test('a lone CR is a line end', () {
      final s = SseFrameSplitter();
      expect(s.add('data: a\r\rdata: b\r\r'), ['data: a']);
      expect(s.finish(), ['data: b']);
    });

    test('finish counts a held final CR', () {
      final s = SseFrameSplitter();
      expect(s.add('data: a\n\r'), isEmpty);
      expect(s.finish(), ['data: a']);
    });

    test('multi-line data, event, id and retry', () {
      final e = parseSseFrame('event: turn\nid: 7\nretry: 3000\ndata: {"a":\ndata: 1}')!;
      expect(e.event, 'turn');
      expect(e.id, '7');
      expect(e.retry, 3000);
      expect(e.data, '{"a":\n1}');
      expect(e.decoded, {'a': 1});
    });

    test('only one leading space is removed; a bare field has an empty value', () {
      expect(parseSseFrame('data:  two')!.data, ' two');
      expect(parseSseFrame('data')!.data, '');
    });

    test('comments and data-less frames dispatch nothing', () {
      expect(parseSseFrame(': keepalive'), isNull);
      expect(parseSseFrame('event: x\nretry: 5'), isNull);
    });

    test('default event is message; non-JSON data stays a string; bad retry ignored', () {
      final e = parseSseFrame('retry: soon\ndata: hello')!;
      expect(e.event, 'message');
      expect(e.retry, isNull);
      expect(e.decoded, 'hello');
    });
  });

  group('ApiClient.sse', () {
    test('streams events, with a chunk split mid-frame and mid-character', () async {
      final bytes = utf8.encode('event: a\ndata: café\r\n\r\n: ping\n\nid: 2\ndata: 1\ndata: 2\n\n');
      final cut = bytes.indexOf(0xc3) + 1; // between the two bytes of the e-acute
      final c = _client((_) => Stream.fromIterable([bytes.sublist(0, cut), bytes.sublist(cut, cut + 6), bytes.sublist(cut + 6)]));
      final events = await c.sse('/stream').toList();
      expect(events.map((e) => (e.event, e.data, e.id)), [
        ('a', 'café', null),
        ('message', '1\n2', '2'),
      ]);
    });

    test('a half frame at the end is dropped', () async {
      final c = _client((_) => _chunks(['data: a\n\ndata: b']));
      expect((await c.sse('/s').toList()).map((e) => e.data), ['a']);
    });

    test('GET without a body, POST with one; asks for an event stream', () async {
      final seen = <http.BaseRequest>[];
      final c = _client((_) => _chunks(['data: x\n\n']), seen: seen, tokens: StaticTokenSource('t'));
      await c.sse('/s').toList();
      await c.sse('/s', body: {'q': 1}).toList();
      expect(seen.map((r) => r.method), ['GET', 'POST']);
      expect(seen.first.headers['Accept'], 'text/event-stream');
      expect(seen.first.headers['Authorization'], 'Bearer t');
    });

    test('a non-2xx opening is thrown as a typed error on the stream', () async {
      final c = _client((_) => _chunks(['{"detail":{"code":"gone","message":"m"}}']), status: 404);
      await expectLater(c.sse('/s').toList(), throwsA(isA<NotFound>().having((e) => e.code, 'code', 'gone')));
    });

    test('a 401 is renewed and the stream opened again', () async {
      final tokens = StaticTokenSource('old');
      var opens = 0;
      final c = ApiClient(
        baseUrl: Uri.parse('https://api.test'),
        tokens: tokens,
        onUnauthorized: () async {
          tokens.token = 'new';
          return SessionRefresh.renewed;
        },
        http: MockClient.streaming((req, _) async {
          opens++;
          return opens == 1
              ? http.StreamedResponse(_chunks(['{"detail":"invalid_token"}']), 401, request: req)
              : http.StreamedResponse(_chunks(['data: ok\n\n']), 200, request: req);
        }),
      );
      expect((await c.sse('/s').toList()).single.data, 'ok');
      expect(opens, 2);
    });

    test('silence beyond idleTimeout ends the stream with a timeout failure', () async {
      final ctrl = StreamController<List<int>>();
      final c = _client((_) => ctrl.stream);
      await expectLater(
        c.sse('/s', idleTimeout: const Duration(milliseconds: 50)).toList(),
        throwsA(isA<NetworkFailure>().having((e) => e.kind, 'kind', NetworkFailureKind.timeout)),
      );
      await ctrl.close();
    });

    test('cancelling stops delivery', () async {
      final ctrl = StreamController<List<int>>();
      final c = _client((_) => ctrl.stream);
      final got = <String>[];
      final sub = c.sse('/s').listen((e) => got.add(e.data));
      ctrl.add(utf8.encode('data: 1\n\n'));
      await Future<void>.delayed(const Duration(milliseconds: 30));
      await sub.cancel();
      expect(got, ['1']);
      await ctrl.close();
    });
  });
}
