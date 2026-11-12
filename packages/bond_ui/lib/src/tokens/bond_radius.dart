import 'package:flutter/painting.dart';

/// Corner radii. The rN values are deprecated aliases of the default
/// `BondShape`; read `BondTokens.of(context).shape` instead. `pill` stays.
abstract final class BondRadius {
  @Deprecated('Use BondTokens.of(context).shape.r4')
  static const double r4 = 4;
  @Deprecated('Use BondTokens.of(context).shape.r8')
  static const double r8 = 8;
  @Deprecated('Use BondTokens.of(context).shape.r12')
  static const double r12 = 12;
  @Deprecated('Use BondTokens.of(context).shape.r16')
  static const double r16 = 16;
  @Deprecated('Use BondTokens.of(context).shape.r20')
  static const double r20 = 20;

  /// Fully rounded ends (chips, pills).
  static const double pill = 999;

  @Deprecated('Use BondTokens.of(context).shape.r4All')
  static const BorderRadius r4All = BorderRadius.all(Radius.circular(r4));
  @Deprecated('Use BondTokens.of(context).shape.r8All')
  static const BorderRadius r8All = BorderRadius.all(Radius.circular(r8));
  @Deprecated('Use BondTokens.of(context).shape.r12All')
  static const BorderRadius r12All = BorderRadius.all(Radius.circular(r12));
  @Deprecated('Use BondTokens.of(context).shape.r16All')
  static const BorderRadius r16All = BorderRadius.all(Radius.circular(r16));
  @Deprecated('Use BondTokens.of(context).shape.r20All')
  static const BorderRadius r20All = BorderRadius.all(Radius.circular(r20));
  static const BorderRadius pillAll =
      BorderRadius.all(Radius.circular(pill));
}
