import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_connections/bond_connections.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

void main() {
  test('WantedSet.fromJson reads every field and tolerates gaps', () {
    final w = WantedSet.fromJson({
      'id': 'mail_send',
      'provider': 'google',
      'label': 'Send mail',
      'scopes': ['a', 'b'],
      'granted': true,
    });
    expect(w.id, 'mail_send');
    expect(w.provider, 'google');
    expect(w.label, 'Send mail');
    expect(w.scopes, ['a', 'b']);
    expect(w.granted, isTrue);
    final bare = WantedSet.fromJson({'id': 'x'});
    expect(bare.scopes, isEmpty);
    expect(bare.granted, isFalse);
  });

  test('ConnectionList: wanted parses from the map form, defaults to empty', () {
    final withSets = ConnectionList.fromJson({
      'connections': [
        {'provider': 'google', 'connected': true},
      ],
      'wanted': [
        {'id': 's', 'provider': 'google', 'label': 'L', 'scopes': ['x'], 'granted': false},
      ],
    });
    expect(withSets.connections.single.provider, 'google');
    expect(withSets.wanted.single.id, 's');
    final legacy = ConnectionList.fromJson([
      {'provider': 'microsoft'},
    ]);
    expect(legacy.connections.single.provider, 'microsoft');
    expect(legacy.wanted, isEmpty);
    expect(const ConnectionList().wanted, isEmpty);
  });

  test('ConnectionReturn.attempt is parsed and cleaned', () {
    final url = Uri.parse('https://x.invalid/p?connection=connected&provider=google&attempt=ab_1-C&keep=1');
    final r = ConnectionReturn.parse(url)!;
    expect(r.attempt, 'ab_1-C');
    expect(ConnectionReturn.cleaned(url).toString(), 'https://x.invalid/p?keep=1');
    expect(ConnectionReturn.parse(Uri.parse('https://x.invalid/?connection=error'))!.attempt, isNull);
  });

  group('ConnectionsApi', () {
    final seen = <http.Request>[];
    ApiClient apiAnswering(Object? body) => ApiClient(
          baseUrl: Uri.parse('http://test.invalid'),
          http: MockClient((r) async {
            seen.add(r);
            return http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});
          }),
        );
    setUp(seen.clear);

    test('wanted() reads the sets from the map answer and listAll() both parts', () async {
      final api = ConnectionsApi(apiAnswering({
        'connections': [
          {'provider': 'google', 'connected': true},
        ],
        'wanted': [
          {'id': 'mail', 'provider': 'google', 'label': 'Mail', 'scopes': ['m'], 'granted': false},
          {'id': 'cal', 'provider': 'google', 'label': 'Calendar', 'granted': true},
        ],
      }));
      final sets = await api.wanted();
      expect(sets.map((w) => w.id), ['mail', 'cal']);
      expect(sets.where((w) => !w.granted).map((w) => w.id), ['mail']);
      final all = await api.listAll();
      expect(all.connections.single.provider, 'google');
      expect(all.wanted, hasLength(2));
      expect(seen.last.url.path, '/connections');
    });

    test('wanted() on an older server (bare array) is empty; a scalar is a BadResponse', () async {
      expect(await ConnectionsApi(apiAnswering([<String, Object?>{'provider': 'google'}])).wanted(), isEmpty);
      await expectLater(ConnectionsApi(apiAnswering(5)).wanted(), throwsA(isA<BadResponse>()));
    });

    test('startUrl adds set as a query parameter, next to redirect_to and mode', () async {
      final api = ConnectionsApi(apiAnswering({'url': 'http://x.test/go'}));
      await api.startUrl('google', set: 'mail');
      expect(seen.last.url.queryParameters, {'set': 'mail'});
      await api.startUrl('google', redirectTo: 'http://app.test/c', native: true, set: 'cal');
      expect(seen.last.url.queryParameters, {'redirect_to': 'http://app.test/c', 'mode': 'native', 'set': 'cal'});
      await api.startUrl('google');
      expect(seen.last.url.hasQuery, isFalse);
    });
  });

  test('ConnectionReturn.cleaned drops attempt and code too, keeps the rest', () {
    final url = Uri.parse('https://x.invalid/p?connection=connected&provider=g&code=c1&attempt=a1&reason=r&keep=1&other=2');
    expect(ConnectionReturn.cleaned(url).queryParameters, {'keep': '1', 'other': '2'});
    final r = ConnectionReturn.parse(url)!;
    expect(r.code, 'c1');
    expect(r.attempt, 'a1');
  });
}
