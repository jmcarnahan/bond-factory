import 'package:bond_api/bond_api.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sdk_demo/src/example_api.dart';
import 'package:sdk_demo/src/pages/api_page.dart';
import 'package:sdk_demo/src/theme.dart';

String _result(WidgetTester t) => t.widget<SelectableText>(find.byKey(const Key('api-result'))).data!;

Future<CannedHttpClient> _pump(WidgetTester t, void Function(CannedResponses) canned) async {
  final client = CannedHttpClient();
  canned(client.responses);
  DemoSession.reset(client: client, base: Uri.parse('http://example.test'));
  addTearDown(DemoSession.reset);
  setWideScreen(t);
  await pumpApp(t, const ApiPage(), theme: buildDemoTheme());
  return client;
}

Future<void> _tap(WidgetTester t, String label) async {
  await t.tap(find.text(label));
  await t.pump();
  await t.pump(const Duration(milliseconds: 50));
}

void main() {
  testWidgets('starts with no call made', (t) async {
    final client = await _pump(t, (_) {});
    expect(_result(t), 'No call yet.');
    expect(client.requests, isEmpty);
    await expectNoOverlays(t);
  });

  testWidgets('health shows the answer as JSON', (t) async {
    final client = await _pump(t, (r) => r.json('GET', '/health', {'status': 'ok', 'mode': 'fake'}));
    await _tap(t, 'Health');
    expect(_result(t), contains('"status": "ok"'));
    expect(_result(t), contains('"mode": "fake"'));
    expect(client.requestsTo('GET', '/health'), hasLength(1));
  });

  testWidgets('not found shows its type, code and message', (t) async {
    await _pump(t, (r) {
      r.json('GET', '/nope', {
        'detail': {'code': 'not_found', 'message': 'Not Found'},
      }, status: 404);
    });
    await _tap(t, 'Not found');
    expect(_result(t), contains('NotFound (404)'));
    expect(_result(t), contains('code: not_found'));
    expect(_result(t), contains('message: Not Found'));
  });

  testWidgets('validation shows the field errors inline', (t) async {
    final client = await _pump(t, (r) {
      r.json('POST', '/auth/firebase', {
        'detail': {
          'code': 'validation_error',
          'message': 'id_token: Field required',
          'errors': [
            {'loc': ['body', 'id_token'], 'msg': 'Field required', 'type': 'missing'},
          ],
        },
      }, status: 422);
    });
    await _tap(t, 'Validation');
    expect(_result(t), contains('ValidationError (422)'));
    expect(_result(t), contains('code: validation_error'));
    expect(_result(t), contains('field id_token: Field required'));
    expect(client.requestsTo('POST', '/auth/firebase').single.json, <String, Object?>{});
  });

  testWidgets('a server that cannot be reached shows a network failure, not a crash', (t) async {
    await _pump(t, (r) => r.fail('GET', '/health', Exception('refused')));
    await _tap(t, 'Health');
    expect(_result(t), isNot('Calling...'));
    expect(_result(t), contains('message:'));
    await expectNoOverlays(t);
  });

  test('describeFailure lists a field per line', () {
    const e = ValidationError('x: bad', fields: {'a': 'one', 'b': 'two'}, code: 'validation_error');
    expect(describeFailure(e), allOf(contains('field a: one'), contains('field b: two')));
  });
}
