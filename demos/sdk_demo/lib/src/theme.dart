import 'package:flutter/material.dart';

/// Plain Material 3 theme from one seed colour. Raw colours live here only.
ThemeData buildDemoTheme() {
  return ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3F51B5)),
  );
}
