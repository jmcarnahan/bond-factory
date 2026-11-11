import 'package:flutter/material.dart';

abstract final class DemoTokens {
  static const Color seed = Color(0xFF2E7D32);
  static const double maxContentWidth = 1100;
  static const double pad = 16;
  static const double gap = 12;
  static const double gapLarge = 24;
  static const double progressHeight = 4;
  static const Color error = Color(0xFFB3261E);

  static const String defaultAddress = '100 Example Ave, Sampletown, CA 90000';
  static const String serviceDefault = 'http://127.0.0.1:8011';
  static const String fixtureAssetDir = 'assets/fixtures/';
  static const Duration pollInterval = Duration(seconds: 2);
  static const Duration jobTimeout = Duration(minutes: 4);
  static const Duration requestTimeout = Duration(seconds: 20);
  static const Duration listTimeout = Duration(seconds: 3);
}
