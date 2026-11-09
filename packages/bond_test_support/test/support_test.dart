import 'dart:async';

import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

void main() {
  group('screen', () {
    testWidgets('setPhone sets logical size and dpr', (t) async {
      setPhone(t, dpr: 2);
      expect(t.view.devicePixelRatio, 2);
      expect(t.view.physicalSize, const Size(780, 1688));
      late Size seen;
      await pumpApp(t, Builder(builder: (c) {
        seen = MediaQuery.sizeOf(c);
        return const SizedBox();
      }));
      expect(seen, const Size(390, 844));
    });

    testWidgets('setWideScreen sets the desktop size', (t) async {
      setWideScreen(t);
      expect(t.view.physicalSize, const Size(1280, 800));
      expect(t.view.devicePixelRatio, 1);
    });
  });

  group('FakeCall', () {
    test('records arguments and serves answers in order', () {
      final f = FakeCall<int>()
        ..returnsInOrder([1, 2])
        ..returns(9);
      expect(f('a'), 1);
      expect(f('b'), 2);
      expect(f('c'), 9);
      expect(f('d'), 9);
      expect(f.calls, ['a', 'b', 'c', 'd']);
      expect(f.count, 4);
      expect(f.last, 'd');
    });

    test('throws a queued error once, then the sticky answer', () {
      final f = FakeCall<int>(result: 5)..throwsOnce(StateError('boom'));
      expect(() => f(), throwsStateError);
      expect(f(), 5);
    });

    test('no answer is a readable StateError; reset clears', () {
      final f = FakeCall<String>();
      expect(() => f(), throwsA(isA<StateError>()));
      f.returns('x');
      f.reset();
      expect(f.wasCalled, isFalse);
      expect(() => f(), throwsA(isA<StateError>()));
    });

    test('callAsync', () async {
      expect(await (FakeCall<int>(result: 3)).callAsync(), 3);
    });
  });

  group('CannedHttpClient', () {
    test('serves by method and path and records requests', () async {
      final c = CannedHttpClient();
      c.responses
        ..json('GET', '/me', {'id': 1})
        ..json('POST', '/items', {'ok': true}, status: 201);
      final r = await c.get(Uri.parse('https://x.test/me?a=1'), headers: {'x-a': 'b'});
      expect(r.statusCode, 200);
      expect(r.body, '{"id":1}');
      final p = await c.post(Uri.parse('https://x.test/items'), body: '{"n":1}');
      expect(p.statusCode, 201);
      expect(c.requests.map((e) => e.toString()), ['GET /me', 'POST /items']);
      expect(c.requests.first.headers['x-a'], 'b');
      expect(c.requestsTo('post', '/items').single.json, {'n': 1});
    });

    test('queue is served in order and the last answer repeats', () async {
      final c = CannedHttpClient();
      c.responses
        ..json('GET', '/a', {'n': 1}, status: 401)
        ..json('GET', '/a', {'n': 2});
      expect((await c.get(Uri.parse('http://h/a'))).statusCode, 401);
      expect((await c.get(Uri.parse('http://h/a'))).statusCode, 200);
      expect((await c.get(Uri.parse('http://h/a'))).statusCode, 200);
    });

    test('unmatched requests get a 404 and are listed', () async {
      final c = CannedHttpClient();
      final r = await c.get(Uri.parse('http://h/none'));
      expect(r.statusCode, 404);
      expect(r.body, contains('no canned response for GET /none'));
      expect(c.unmatched, hasLength(1));
    });

    test('a failing answer throws', () async {
      final c = CannedHttpClient();
      c.responses.fail('GET', '/x', http.ClientException('down'));
      await expectLater(c.get(Uri.parse('http://h/x')), throwsA(isA<http.ClientException>()));
    });

    test('close is recorded', () {
      final c = CannedHttpClient()..close();
      expect(c.closed, isTrue);
    });
  });

  group('waits', () {
    testWidgets('pumpUntil returns when the finder matches', (t) async {
      var shown = false;
      late StateSetter set;
      await pumpApp(t, StatefulBuilder(builder: (c, s) {
        set = s;
        return shown ? const Text('ready') : const SizedBox();
      }));
      Timer(const Duration(milliseconds: 300), () => set(() => shown = true));
      await pumpUntil(t, find.text('ready'));
      expect(find.text('ready'), findsOneWidget);
    });

    testWidgets('pumpUntil times out with a readable message', (t) async {
      await pumpApp(t, const SizedBox());
      Object? caught;
      try {
        await pumpUntil(t, find.text('never'), timeout: const Duration(milliseconds: 200));
      } catch (e) {
        caught = e;
      }
      expect(caught, isA<TestFailure>());
      expect((caught! as TestFailure).message, allOf(contains('200 ms'), contains('never')));
    });

    test('pollUntil returns the first non-null value', () async {
      var n = 0;
      final v = await pollUntil<int>(() async => ++n >= 3 ? n : null, every: const Duration(milliseconds: 1));
      expect(v, 3);
    });

    test('pollUntil fails at the cap', () async {
      await expectLater(
        pollUntil<int>(() async => null,
            timeout: const Duration(milliseconds: 30), every: const Duration(milliseconds: 5), what: 'row'),
        throwsA(isA<TestFailure>().having((e) => e.message, 'message', contains('waiting for row'))),
      );
    });

    test('Emissions collects, waits and times out', () async {
      final ctrl = StreamController<int>();
      final e = Emissions<int>(ctrl.stream);
      final waiting = e.take(2);
      ctrl.add(1);
      ctrl.add(2);
      expect(await waiting, [1, 2]);
      ctrl.addError('bad');
      await e.until(() => e.errors.isNotEmpty);
      expect(e.errors, ['bad']);
      await expectLater(
        e.until(() => e.values.length > 5, what: 'six values', timeout: const Duration(milliseconds: 30)),
        throwsA(isA<TestFailure>()),
      );
      await ctrl.close();
      await e.untilDone();
      expect(e.done, isTrue);
    });
  });
}
