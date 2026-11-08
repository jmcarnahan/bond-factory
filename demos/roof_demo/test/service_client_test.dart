import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:roof_demo/src/service_client.dart';

ServiceClient _client(http.Response Function(http.Request) h) =>
    ServiceClient(baseUrl: 'http://test', client: MockClient((r) async => h(r)));

void main() {
  test('fixtures() reads the service object list as stems', () async {
    final c = _client((_) => http.Response(
        '[{"name":"site1_truth","file":"site1_truth.json","bytes":10},'
        '{"name":"synthetic_hip","file":"synthetic_hip.json","bytes":20}]',
        200));
    expect(await c.fixtures(), ['site1_truth', 'synthetic_hip']);
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
}
