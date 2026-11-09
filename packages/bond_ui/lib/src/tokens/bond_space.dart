import 'package:flutter/widgets.dart';

/// Spacing scale. Plain constants: spacing is not brand-specific.
abstract final class BondSpace {
  static const double s4 = 4;
  static const double s8 = 8;
  static const double s12 = 12;
  static const double s16 = 16;
  static const double s20 = 20;
  static const double s24 = 24;
  static const double s32 = 32;
  static const double s40 = 40;
  static const double s48 = 48;
  static const double s64 = 64;

  // Vertical gaps.
  static const Widget h4 = SizedBox(height: s4);
  static const Widget h8 = SizedBox(height: s8);
  static const Widget h12 = SizedBox(height: s12);
  static const Widget h16 = SizedBox(height: s16);
  static const Widget h24 = SizedBox(height: s24);
  static const Widget h32 = SizedBox(height: s32);

  // Horizontal gaps.
  static const Widget w4 = SizedBox(width: s4);
  static const Widget w8 = SizedBox(width: s8);
  static const Widget w12 = SizedBox(width: s12);
  static const Widget w16 = SizedBox(width: s16);
  static const Widget w24 = SizedBox(width: s24);

  // Common paddings.
  static const EdgeInsets all4 = EdgeInsets.all(s4);
  static const EdgeInsets all8 = EdgeInsets.all(s8);
  static const EdgeInsets all12 = EdgeInsets.all(s12);
  static const EdgeInsets all16 = EdgeInsets.all(s16);
  static const EdgeInsets all20 = EdgeInsets.all(s20);
  static const EdgeInsets all24 = EdgeInsets.all(s24);

  /// Page padding on a wide screen.
  static const EdgeInsets page =
      EdgeInsets.symmetric(horizontal: s32, vertical: s24);

  /// Page padding on a phone.
  static const EdgeInsets pageMobile =
      EdgeInsets.symmetric(horizontal: s16, vertical: s16);
}
