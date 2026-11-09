import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_connections/bond_connections.dart';
import 'package:bond_json/bond_json.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

Map<String, Object?> row({
  String provider = 'fake-google',
  bool connected = false,
  String? email,
  String? at,
  bool needs = false,
  Object? scopes = const <String>[],
}) =>
    {'provider': provider, 'connected': connected, 'email': email, 'connected_at': at, 'needs_reconnect': needs, 'scopes': scopes};

class Fake {
  final List<http.Request> seen = [];
  Object? body = <Object?>[];
  int status = 200;

  late final ApiClient api = ApiClient(
    baseUrl: Uri.parse('http://test.invalid'),
    http: MockClient((r) async {
      seen.add(r);
      return http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});
    }),
  );
}

void main() {
  group('ConnectionStatus', () {
    test('reads every field of the wire row', () {
      final s = ConnectionStatus.fromJson(row(
        connected: true,
        email: 'demo@example.com',
        at: '2026-11-08T17:04:05Z',
        scopes: 'openid email',
      ));
      expect(s.provider, 'fake-google');
      expect(s.connected, isTrue);
      expect(s.email, 'demo@example.com');
      expect(s.connectedAt, DateTime.utc(2026, 11, 8, 17, 4, 5));
      expect(s.scopes, ['openid', 'email']);
    });

    test('scopes also read as a list, and missing keys read as empty', () {
      expect(ConnectionStatus.fromJson(row(scopes: ['a', 'b'])).scopes, ['a', 'b']);
      final bare = ConnectionStatus.fromJson({'provider': 'google'});
      expect(bare.connected, isFalse);
      expect(bare.email, isNull);
      expect(bare.connectedAt, isNull);
      expect(bare.scopes, isEmpty);
    });

    test('a value of the wrong type throws JsonShapeError', () {
      expect(() => ConnectionStatus.fromJson({'provider': 'x', 'connected': 'yes'}), throwsA(isA<JsonShapeError>()));
      expect(() => ConnectionStatus.fromJson('nope'), throwsA(isA<JsonShapeError>()));
    });

    test('phase is derived: disconnected, connected, needs reconnect', () {
      expect(ConnectionStatus.fromJson(row()).phase, ConnectionPhase.disconnected);
      expect(ConnectionStatus.fromJson(row(connected: true)).phase, ConnectionPhase.connected);
      expect(ConnectionStatus.fromJson(row(connected: true, needs: true)).phase, ConnectionPhase.needsReconnect);
    });

    test('needs_reconnect without connected still derives needsReconnect', () {
      final s = ConnectionStatus.fromJson(row(needs: true));
      expect(s.connected, isFalse);
      expect(s.phase, ConnectionPhase.needsReconnect);
    });

    test('toJson round trips and equality compares values', () {
      final s = ConnectionStatus.fromJson(row(connected: true, email: 'a@example.com', at: '2026-11-08T10:00:00Z', scopes: 'x y'));
      expect(ConnectionStatus.fromJson(s.toJson()), s);
      expect(s.hashCode, ConnectionStatus.fromJson(s.toJson()).hashCode);
    });
  });

  group('ConnectionsApi', () {
    test('list is GET /connections and maps every row', () async {
      final f = Fake()..body = [row(), row(provider: 'fake-microsoft', connected: true, email: 'a@example.com')];
      final all = await ConnectionsApi(f.api).list();
      expect(f.seen.single.method, 'GET');
      expect(f.seen.single.url.path, '/connections');
      expect(all.map((s) => s.provider), ['fake-google', 'fake-microsoft']);
      expect(all.last.phase, ConnectionPhase.connected);
    });

    test('list of an object or a bad row is a BadResponse', () async {
      final f = Fake()..body = {'detail': 'x'};
      await expectLater(ConnectionsApi(f.api).list(), throwsA(isA<BadResponse>()));
      f.body = [
        {'provider': 5},
      ];
      await expectLater(ConnectionsApi(f.api).list(), throwsA(isA<BadResponse>()));
    });

    test('startUrl is GET .../start with redirect_to and returns the url', () async {
      final f = Fake()..body = {'url': 'http://api.test/connections/fake-google/go?state=abc'};
      final url = await ConnectionsApi(f.api).startUrl('fake-google', redirectTo: 'http://app.test/connections');
      expect(f.seen.single.method, 'GET');
      expect(f.seen.single.url.path, '/connections/fake-google/start');
      expect(f.seen.single.url.queryParameters, {'redirect_to': 'http://app.test/connections'});
      expect(url.path, '/connections/fake-google/go');
      expect(url.queryParameters['state'], 'abc');
    });

    test('startUrl without redirectTo sends no query; an answer with no url fails', () async {
      final f = Fake()..body = {'url': 'http://x.test/go'};
      await ConnectionsApi(f.api).startUrl('google');
      expect(f.seen.single.url.hasQuery, isFalse);
      f.body = <String, Object?>{};
      await expectLater(ConnectionsApi(f.api).startUrl('google'), throwsA(isA<BadResponse>()));
    });

    test('startUrl native adds mode=native next to redirect_to', () async {
      final f = Fake()..body = {'url': 'http://x.test/go?state=s'};
      await ConnectionsApi(f.api)
          .startUrl('google', redirectTo: 'sdkdemo://connections', native: true, deviceChallenge: 'dc', attempt: 'at');
      expect(f.seen.single.url.queryParameters, {
        'redirect_to': 'sdkdemo://connections',
        'mode': 'native',
        'device_challenge': 'dc',
        'attempt': 'at',
      });
      await ConnectionsApi(f.api).startUrl('google', native: true, deviceChallenge: 'dc', attempt: 'at');
      expect(f.seen.last.url.queryParameters, {'mode': 'native', 'device_challenge': 'dc', 'attempt': 'at'});
    });

    test('redeem is POST .../redeem with the code and reads the status', () async {
      final f = Fake()..body = row(connected: true, email: 'demo@example.com');
      final s = await ConnectionsApi(f.api).redeem('fake-google', 'abc.def', deviceSecret: 'sec');
      expect(f.seen.single.method, 'POST');
      expect(f.seen.single.url.path, '/connections/fake-google/redeem');
      expect(jsonDecode(f.seen.single.body), {'code': 'abc.def', 'device_secret': 'sec'});
      expect(s.phase, ConnectionPhase.connected);
    });

    test('redeem sends the optional device_label', () async {
      final f = Fake()..body = row(connected: true);
      await ConnectionsApi(f.api).redeem('google', 'c', deviceSecret: 's', deviceLabel: 'Phone');
      expect(jsonDecode(f.seen.single.body), {'code': 'c', 'device_secret': 's', 'device_label': 'Phone'});
    });

    test('native start sends device_challenge and attempt; a missing one is an ArgumentError', () async {
      final f = Fake()..body = {'url': 'http://x.test/go'};
      final api = ConnectionsApi(f.api);
      await api.startUrl('google', native: true, deviceChallenge: 'abc123', attempt: 'att_1', set: 'mail');
      expect(f.seen.single.url.queryParameters, {
        'mode': 'native',
        'device_challenge': 'abc123',
        'attempt': 'att_1',
        'set': 'mail',
      });
      expect(() => api.startUrl('google', native: true, attempt: 'a'), throwsArgumentError);
      expect(() => api.startUrl('google', native: true, deviceChallenge: 'c'), throwsArgumentError);
      expect(() => api.startUrl('google', native: true), throwsArgumentError);
      expect(f.seen, hasLength(1)); // the refused calls sent nothing
    });

    test('web start ignores device arguments', () async {
      final f = Fake()..body = {'url': 'http://x.test/go'};
      await ConnectionsApi(f.api).startUrl('google', deviceChallenge: 'c', attempt: 'a');
      expect(f.seen.single.url.hasQuery, isFalse);
    });

    test('redeem maps a refused code to an ApiException subtype', () async {
      final f = Fake()
        ..status = 400
        ..body = {'detail': {'code': 'invalid_handoff', 'message': 'no'}};
      await expectLater(ConnectionsApi(f.api).redeem('google', 'x', deviceSecret: 's'), throwsA(isA<ApiException>()));
    });

    test('disconnect is DELETE /connections/{provider} and reads the status', () async {
      final f = Fake()..body = row();
      final s = await ConnectionsApi(f.api).disconnect('fake-google');
      expect(f.seen.single.method, 'DELETE');
      expect(f.seen.single.url.path, '/connections/fake-google');
      expect(s.phase, ConnectionPhase.disconnected);
    });

    test('a custom prefix is used, and the provider is path-encoded', () async {
      final f = Fake()..body = row();
      await ConnectionsApi(f.api, prefix: '/v1/links').disconnect('a b');
      expect(f.seen.single.url.path, '/v1/links/a%20b');
    });

    test('an API error surfaces as the typed exception', () async {
      final f = Fake()
        ..status = 403
        ..body = {'detail': {'code': 'forbidden', 'message': 'no'}};
      await expectLater(ConnectionsApi(f.api).startUrl('google'), throwsA(isA<Forbidden>()));
    });

    test('simulateExpiry is POST .../simulate-expiry and reads the status', () async {
      final f = Fake()..body = row(connected: true, needs: true);
      final s = await DemoConnectionsApi(f.api).simulateExpiry('fake-google');
      expect(f.seen.single.method, 'POST');
      expect(f.seen.single.url.path, '/connections/fake-google/simulate-expiry');
      expect(s.phase, ConnectionPhase.needsReconnect);
    });
  });

  group('ConnectionReturn', () {
    test('parse reads the native hand-off code; cleaned drops it', () {
      final u = Uri.parse('sdkdemo://connections?connection=connected&provider=google&code=abc.def&keep=1');
      final r = ConnectionReturn.parse(u)!;
      expect(r.code, 'abc.def');
      expect(r.provider, 'google');
      expect(ConnectionReturn.cleaned(u).queryParameters, {'keep': '1'});
      expect(ConnectionReturn.parse(Uri.parse('http://app.test/c?connection=connected'))!.code, isNull);
    });

    test('reads connected and the provider', () {
      final r = ConnectionReturn.parse(Uri.parse('http://app.test/connections?connection=connected&provider=fake-google'))!;
      expect(r.outcome, ConnectionOutcome.connected);
      expect(r.provider, 'fake-google');
      expect(r.reason, isNull);
      expect(r.isError, isFalse);
    });

    test('reads an error with its reason', () {
      final r = ConnectionReturn.parse(Uri.parse('/connections?connection=error&provider=google&reason=access_denied'))!;
      expect(r.isError, isTrue);
      expect(r.reason, 'access_denied');
    });

    test('absent, unknown or empty parameters give null or null fields', () {
      expect(ConnectionReturn.parse(Uri.parse('http://app.test/connections')), isNull);
      expect(ConnectionReturn.parse(Uri.parse('http://app.test/connections?connection=maybe')), isNull);
      expect(ConnectionReturn.parse(Uri.parse('http://app.test/connections?provider=google')), isNull);
      final r = ConnectionReturn.parse(Uri.parse('http://app.test/connections?connection=connected&provider='))!;
      expect(r.provider, isNull);
    });

    test('cleaned drops only the three return parameters', () {
      final u = ConnectionReturn.cleaned(Uri.parse('http://app.test/connections?connection=error&provider=g&reason=x&keep=1'));
      expect(u.queryParameters, {'keep': '1'});
      expect(ConnectionReturn.cleaned(Uri.parse('http://app.test/connections?connection=connected')).hasQuery, isFalse);
    });
  });

  group('ConnectionLabels', () {
    test('names, titles and reasons fall back sensibly', () {
      const l = ConnectionLabels(providerNames: {'google': 'Google'});
      expect(l.providerName('google'), 'Google');
      expect(l.providerName('fake-google'), 'fake-google');
      expect(l.connectedTitleFor('google'), 'Google connected');
      expect(l.errorTitleFor(null), 'Could not connect the provider');
      expect(l.reasonText('access_denied'), 'Access was declined.');
      expect(l.reasonText('not_confirmed'), startsWith('Nothing changed'));
      expect(l.reasonText('weird'), l.returnErrorGeneric);
      expect(l.reasonText(null), l.returnErrorGeneric);
    });

    test('every known return reason has its own text', () {
      const l = ConnectionLabels();
      const known = ['access_denied', 'unavailable', 'invalid_state', 'expired_state', 'not_confirmed', 'account_mismatch', 'consent_declined', 'forbidden'];
      for (final r in known) {
        expect(l.reasonText(r), isNot(l.returnErrorGeneric), reason: r);
      }
      expect(l.reasonText('consent_declined'), 'You did not allow that access. You can allow it later.');
      expect(l.reasonText('account_mismatch'), 'That is a different account than the one you signed in with.');
    });
  });
}
