/// A minimal app around the widget under test.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Pumps [child] inside a MaterialApp and Scaffold body, then settles one frame.
Future<void> pumpApp(WidgetTester t, Widget child, {ThemeData? theme}) async {
  await t.pumpWidget(MaterialApp(theme: theme, home: Scaffold(body: child)));
}
