/// Test window sizes.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

/// Sets the test window to [size] logical pixels at pixel ratio [dpr] and
/// restores the defaults at teardown.
void _setView(WidgetTester t, Size size, double dpr) {
  t.view.devicePixelRatio = dpr;
  t.view.physicalSize = Size(size.width * dpr, size.height * dpr);
  addTearDown(t.view.resetPhysicalSize);
  addTearDown(t.view.resetDevicePixelRatio);
}

/// A phone: 390 x 844 logical pixels by default (a current iPhone).
void setPhone(WidgetTester t, {double dpr = 1, Size size = const Size(390, 844)}) => _setView(t, size, dpr);

/// A desktop window: 1280 x 800 logical pixels by default, pixel ratio 1.
void setWideScreen(WidgetTester t, {Size size = const Size(1280, 800)}) => _setView(t, size, 1);
