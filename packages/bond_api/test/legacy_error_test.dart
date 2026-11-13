// A legacy host's error body (upper-case error_code beside the lower-case code).
import 'dart:convert';
import 'dart:io';

import 'package:bond_api/bond_api.dart';
import 'package:test/test.dart';

void main() {
  test('error_not_owner.json yields the lower-case code and the message', () {
    final raw = File('../../fixtures/legacy_host/error_not_owner.json').readAsStringSync();
    for (final body in [jsonDecode(raw), raw]) {
      final e = ErrorBody.parse(403, body) as Forbidden;
      expect(e.code, 'not_task_owner');
      expect(e.message, 'Only the owner can link a task to a client or case.');
    }
  });
}
