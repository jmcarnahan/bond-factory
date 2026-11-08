import 'dart:convert';

import 'package:http/http.dart' as http;

import 'tokens.dart';

enum MeasureMethod {
  lidar('lidar_skeleton', 'LiDAR'),
  lidarAgent('lidar_agent', 'LiDAR + agent'),
  solarAgent('solar_agent', 'Solar + agent');

  const MeasureMethod(this.wire, this.label);
  final String wire;
  final String label;
}

/// Thin client for the roof measure service.
class ServiceClient {
  ServiceClient({String? baseUrl, http.Client? client})
      : base = baseUrl ?? const String.fromEnvironment('ROOF_SERVICE', defaultValue: DemoTokens.serviceDefault),
        _http = client ?? http.Client();

  final String base;
  final http.Client _http;

  Future<Map<String, dynamic>> measureJson(String address, MeasureMethod method) async {
    final res = await _http
        .post(
          Uri.parse('$base/measure'),
          headers: {'content-type': 'application/json'},
          body: jsonEncode({'address': address, 'method': method.wire}),
        )
        .timeout(DemoTokens.measureTimeout);
    if (res.statusCode != 200) {
      throw 'Service answered ${res.statusCode}: ${_short(res.body)}';
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Fixture stems (no `.json`) the service offers, or empty when it is not
  /// reachable or answers with an unexpected shape. The service returns a list
  /// of `{name, file, bytes}` objects; a plain list of strings is tolerated.
  Future<List<String>> fixtures() async {
    try {
      final res = await _http.get(Uri.parse('$base/fixtures')).timeout(DemoTokens.listTimeout);
      if (res.statusCode != 200) return const [];
      return parseFixtureNames(jsonDecode(res.body));
    } catch (_) {
      return const [];
    }
  }

  /// Normalises a decoded /fixtures body to a list of stems. Returns const []
  /// on any shape it does not understand.
  static List<String> parseFixtureNames(Object? body) {
    if (body is! List) return const [];
    final out = <String>[];
    for (final e in body) {
      final Object? raw = e is Map ? e['name'] : e;
      if (raw is! String || raw.isEmpty) return const [];
      out.add(fixtureStem(raw));
    }
    return out;
  }

  static String fixtureStem(String name) =>
      name.endsWith('.json') ? name.substring(0, name.length - '.json'.length) : name;

  Future<Map<String, dynamic>> fixtureJson(String name) async {
    final res = await _http.get(Uri.parse('$base/fixtures/${fixtureStem(name)}')).timeout(DemoTokens.listTimeout);
    if (res.statusCode != 200) throw 'Service answered ${res.statusCode}';
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  static String _short(String s) => s.length > 300 ? '${s.substring(0, 300)}...' : s;
}
