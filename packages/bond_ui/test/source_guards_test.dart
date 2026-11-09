import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Source-level rules for bond_ui: raw colours only in lib/src/tokens/, no
/// popups anywhere, no intl or riverpod.
void main() {
  final files = Directory('lib')
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'))
      .toList();

  List<String> hits(RegExp pattern, {bool Function(String path)? skip}) {
    final out = <String>[];
    for (final f in files) {
      if (skip != null && skip(f.path)) continue;
      final lines = f.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
        if (line.trimLeft().startsWith('//')) continue;
        if (pattern.hasMatch(line)) out.add('${f.path}:${i + 1}: ${line.trim()}');
      }
    }
    return out;
  }

  test('the scan sees the sources', () {
    expect(files.length, greaterThan(30));
  });

  test('no raw colours outside lib/src/tokens/', () {
    final found = hits(
      RegExp(r'Colors\.|Color\(0x|Color\.from'),
      skip: (p) => p.contains('/tokens/'),
    );
    expect(found, isEmpty, reason: found.join('\n'));
  });

  test('no popups, dialogs, dropdowns, menus, snack bars or tooltips', () {
    final found = hits(RegExp(
      r'showDatePicker|showTimePicker|showDialog|showModalBottomSheet|'
      r'showBottomSheet|DropdownButton|PopupMenu|SnackBar|Tooltip\(|'
      r'AlertDialog|showMenu|MenuAnchor|Autocomplete',
    ));
    expect(found, isEmpty, reason: found.join('\n'));
  });

  test('no intl, riverpod, go_router or localizations imports', () {
    final found = hits(RegExp(
      r"import\s+'package:(intl|flutter_riverpod|riverpod|go_router|flutter_localizations)/",
    ));
    expect(found, isEmpty, reason: found.join('\n'));
  });

  test('no brand names leaked into the sources', () {
    final words = hits(
        RegExp(r'avalon|sbel|pagatime|paga-time|bondable', caseSensitive: false));
    final prefixes = hits(RegExp(r'\bAv[A-Z]|\bPt[A-Z]|\bSbel'));
    final found = [...words, ...prefixes];
    expect(found, isEmpty, reason: found.join('\n'));
  });
}
