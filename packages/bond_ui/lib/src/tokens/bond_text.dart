import 'package:flutter/material.dart';

import 'bond_tokens.dart';

/// Type scale built from a [BondTokens]: sizes and weights are constants,
/// colours and the font family come from the tokens.
@immutable
class BondText {
  const BondText(this.tokens);

  /// The scale for the tokens in scope.
  factory BondText.of(BuildContext context) =>
      BondText(BondTokens.of(context));

  final BondTokens tokens;

  // Sizes. All raw font sizes live here.
  static const double caption12 = 12;
  static const double label13 = 13;
  static const double small14 = 14;
  static const double body15 = 15;
  static const double base16 = 16;
  static const double lead18 = 18;
  static const double title20 = 20;
  static const double heading28 = 28;
  static const double display40 = 40;

  // Weights.
  static const FontWeight regular = FontWeight.w400;
  static const FontWeight medium = FontWeight.w500;
  static const FontWeight semibold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;

  static const List<String> _monoFallback = [
    'Menlo',
    'Roboto Mono',
    'Courier New',
    'monospace',
  ];

  /// A style in the token font. [tight] gives headings tighter tracking and
  /// leading; running text uses 1.5 leading.
  TextStyle style(
    double size,
    FontWeight weight, {
    Color? color,
    bool tight = false,
  }) =>
      TextStyle(
        fontFamily: tokens.fontFamily,
        package: tokens.fontPackage,
        fontSize: size,
        fontWeight: weight,
        color: color ?? tokens.ink,
        height: tight ? 1.2 : 1.5,
        letterSpacing: tight ? size * -0.02 : 0,
      );

  /// 13 / 600 / +0.08em. Callers upper-case the text.
  TextStyle get eyebrow => TextStyle(
        fontFamily: tokens.fontFamily,
        package: tokens.fontPackage,
        fontSize: label13,
        fontWeight: semibold,
        color: tokens.muted,
        height: 1.5,
        letterSpacing: label13 * 0.08,
      );

  TextStyle get body => style(base16, regular, color: tokens.body);
  TextStyle get bodyStrong => style(base16, semibold);
  TextStyle get small => style(small14, regular, color: tokens.body);
  TextStyle get smallStrong => style(small14, semibold);
  TextStyle get label => style(label13, medium, color: tokens.muted);
  TextStyle get caption => style(caption12, regular, color: tokens.muted);
  TextStyle get lead => style(lead18, semibold);
  TextStyle get title => style(title20, semibold, tight: true);
  TextStyle get heading => style(heading28, bold, tight: true);
  TextStyle get display => style(display40, bold, tight: true);

  /// Fixed-width text (codes, ids). Ignores the token font.
  TextStyle get mono => TextStyle(
        fontFamily: 'monospace',
        fontFamilyFallback: _monoFallback,
        fontSize: small14,
        fontWeight: regular,
        color: tokens.body,
        height: 1.5,
      );

  /// Material text theme for [BondTokens]; used by `BondTheme.build`.
  static TextTheme textTheme(BondTokens tokens) {
    final t = BondText(tokens);
    return TextTheme(
      displayLarge: t.display,
      headlineLarge: t.heading,
      titleLarge: t.title,
      titleMedium: t.lead,
      titleSmall: t.smallStrong,
      bodyLarge: t.body,
      bodyMedium: t.small,
      bodySmall: t.caption,
      labelLarge: t.smallStrong,
      labelMedium: t.label,
      labelSmall: t.caption,
    );
  }
}
