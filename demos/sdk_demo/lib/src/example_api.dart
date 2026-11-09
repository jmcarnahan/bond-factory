import 'dart:convert';

import 'package:http/http.dart' as http;

/// Phase 1 session: a plain health probe against the example API.
/// Phase 2 replaces this file with one shared ApiClient and an AuthGateway.
class DemoSession {
  const DemoSession._();

  /// Base URL of the example API; override with `--dart-define=SDK_EXAMPLE_URL=...`.
  static Uri baseUrl = Uri.parse(
    const String.fromEnvironment(
      'SDK_EXAMPLE_URL',
      defaultValue: 'http://localhost:8012',
    ),
  );

  /// `GET /health`, decoded. Throws [StateError] on a non-200 answer.
  static Future<Map<String, Object?>> health() async {
    final response = await http.get(baseUrl.resolve('/health'));
    if (response.statusCode != 200) {
      throw StateError('health returned ${response.statusCode}');
    }
    return Map<String, Object?>.from(jsonDecode(response.body) as Map);
  }
}
