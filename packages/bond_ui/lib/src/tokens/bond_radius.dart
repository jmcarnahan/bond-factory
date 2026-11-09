import 'package:flutter/painting.dart';

/// Corner radii.
abstract final class BondRadius {
  static const double r4 = 4;
  static const double r8 = 8;
  static const double r12 = 12;
  static const double r16 = 16;
  static const double r20 = 20;

  /// Fully rounded ends (chips, pills).
  static const double pill = 999;

  static const BorderRadius r4All = BorderRadius.all(Radius.circular(r4));
  static const BorderRadius r8All = BorderRadius.all(Radius.circular(r8));
  static const BorderRadius r12All = BorderRadius.all(Radius.circular(r12));
  static const BorderRadius r16All = BorderRadius.all(Radius.circular(r16));
  static const BorderRadius r20All = BorderRadius.all(Radius.circular(r20));
  static const BorderRadius pillAll =
      BorderRadius.all(Radius.circular(pill));
}
