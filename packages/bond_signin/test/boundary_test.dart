import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('lib imports no Flutter and no dart:io', () {
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'))) {
      final s = f.readAsStringSync();
      expect(s, isNot(contains('package:flutter')), reason: f.path);
      expect(s, isNot(contains('dart:io')), reason: f.path);
      expect(s, isNot(contains('dart:ui')), reason: f.path);
    }
  });

  test('randomness is secure: no Random() without .secure or a test seed in lib', () {
    final attempt = File('lib/src/sign_in_attempt.dart').readAsStringSync();
    expect(attempt, contains('Random.secure()'));
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'))) {
      expect(RegExp(r'\bRandom\(').hasMatch(f.readAsStringSync()), isFalse, reason: f.path);
    }
  });
}
