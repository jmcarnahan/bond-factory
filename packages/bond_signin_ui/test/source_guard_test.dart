import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final files = Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart')).toList();

  test('there are source files to guard', () => expect(files, isNotEmpty));

  test('no dialogs, sheets, snack bars or menus', () {
    final banned = RegExp(r'showDialog|showModalBottomSheet|showBottomSheet|showSnackBar|showMenu|AlertDialog|SimpleDialog|PopupMenuButton|DropdownButton|Tooltip\(|showDatePicker|showTimePicker|WebView');
    for (final f in files) {
      expect(banned.hasMatch(f.readAsStringSync()), isFalse, reason: f.path);
    }
  });

  test('no raw colours: tokens only', () {
    final raw = RegExp(r'\bColors\.|\bColor\(|\bCupertinoColors\.');
    for (final f in files) {
      expect(raw.hasMatch(f.readAsStringSync()), isFalse, reason: f.path);
    }
  });

  test('no file passes the line cap', () {
    for (final f in files) {
      expect(f.readAsLinesSync().length, lessThanOrEqualTo(300), reason: f.path);
    }
  });
}
