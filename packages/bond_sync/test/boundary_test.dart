import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('lib/ imports no database, Flutter or dart:io', () {
    final forbidden = RegExp(r'''^\s*(import|export)\s+['"](package:(powersync|sqlite|flutter)\b|dart:(io|ui))''');
    final offenders = <String>[];
    var files = 0;
    for (final f in Directory('lib').listSync(recursive: true).whereType<File>()) {
      if (!f.path.endsWith('.dart')) continue;
      files += 1;
      for (final line in f.readAsLinesSync()) {
        if (forbidden.hasMatch(line)) offenders.add('${f.path}: $line');
      }
    }
    expect(files, greaterThan(10));
    expect(offenders, isEmpty);
  });

  test('pubspec has no powersync or flutter dependency', () {
    final text = File('pubspec.yaml').readAsStringSync();
    expect(text, isNot(contains('powersync')));
    expect(text, isNot(contains('sdk: flutter')));
  });
}
