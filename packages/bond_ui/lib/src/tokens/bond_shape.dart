import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

/// Themable corner radii. Defaults equal the old `BondRadius` constants.
/// An app sets its own on `BondTokens.shape`; widgets read it with
/// `BondTokens.of(context).shape`. Fully rounded ends stay on
/// `BondRadius.pill` and `BondRadius.pillAll`.
@immutable
class BondShape {
  const BondShape({
    this.r4 = 4,
    this.r8 = 8,
    this.r12 = 12,
    this.r16 = 16,
    this.r20 = 20,
  });

  final double r4;
  final double r8;
  final double r12;
  final double r16;
  final double r20;

  BorderRadius get r4All => BorderRadius.circular(r4);
  BorderRadius get r8All => BorderRadius.circular(r8);
  BorderRadius get r12All => BorderRadius.circular(r12);
  BorderRadius get r16All => BorderRadius.circular(r16);
  BorderRadius get r20All => BorderRadius.circular(r20);

  BondShape copyWith({
    double? r4,
    double? r8,
    double? r12,
    double? r16,
    double? r20,
  }) => BondShape(
    r4: r4 ?? this.r4,
    r8: r8 ?? this.r8,
    r12: r12 ?? this.r12,
    r16: r16 ?? this.r16,
    r20: r20 ?? this.r20,
  );

  static BondShape lerp(BondShape a, BondShape b, double t) => BondShape(
    r4: a.r4 + (b.r4 - a.r4) * t,
    r8: a.r8 + (b.r8 - a.r8) * t,
    r12: a.r12 + (b.r12 - a.r12) * t,
    r16: a.r16 + (b.r16 - a.r16) * t,
    r20: a.r20 + (b.r20 - a.r20) * t,
  );

  @override
  bool operator ==(Object other) =>
      other is BondShape &&
      other.r4 == r4 &&
      other.r8 == r8 &&
      other.r12 == r12 &&
      other.r16 == r16 &&
      other.r20 == r20;

  @override
  int get hashCode => Object.hash(r4, r8, r12, r16, r20);
}
