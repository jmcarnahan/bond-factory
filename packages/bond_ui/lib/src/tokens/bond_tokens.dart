import 'package:flutter/material.dart';

import 'bond_tone_role.dart';

/// One semantic colour family: a solid fill ([base]), its pressed or text
/// shade ([press]), a pale background ([wash]) and a slightly stronger pale
/// shade for borders and selected states ([soft]).
@immutable
class BondTone {
  const BondTone({
    required this.base,
    required this.press,
    required this.wash,
    required this.soft,
  });

  final Color base;
  final Color press;
  final Color wash;
  final Color soft;

  BondTone copyWith({Color? base, Color? press, Color? wash, Color? soft}) =>
      BondTone(
        base: base ?? this.base,
        press: press ?? this.press,
        wash: wash ?? this.wash,
        soft: soft ?? this.soft,
      );

  static BondTone lerp(BondTone a, BondTone b, double t) => BondTone(
        base: Color.lerp(a.base, b.base, t)!,
        press: Color.lerp(a.press, b.press, t)!,
        wash: Color.lerp(a.wash, b.wash, t)!,
        soft: Color.lerp(a.soft, b.soft, t)!,
      );

  @override
  bool operator ==(Object other) =>
      other is BondTone &&
      other.base == base &&
      other.press == press &&
      other.wash == wash &&
      other.soft == soft;

  @override
  int get hashCode => Object.hash(base, press, wash, soft);
}

/// Resolved colours of a tone for a pill, banner or row.
@immutable
class BondToneColors {
  const BondToneColors({
    required this.background,
    required this.foreground,
    required this.border,
  });

  final Color background;
  final Color foreground;
  final Color border;
}

/// The colours and font of one app. An app builds one [BondTokens] and hands
/// it to `BondScope` (or `BondTheme.build`); every bond widget reads it with
/// [BondTokens.of]. Raw colours live only in `lib/src/tokens/`.
@immutable
class BondTokens extends ThemeExtension<BondTokens> {
  const BondTokens({
    required this.ink,
    required this.body,
    required this.muted,
    required this.line,
    required this.lineStrong,
    required this.ground,
    required this.surface,
    required this.accent,
    required this.danger,
    required this.positive,
    required this.caution,
    required this.info,
    this.onFill = _white,
    this.shadow = _shadow,
    this.fontFamily,
    this.fontPackage,
    this.personPalette = _people,
  });

  /// Strongest text and icons.
  final Color ink;

  /// Running text.
  final Color body;

  /// Secondary text, hints, disabled labels.
  final Color muted;

  /// Hairlines and dividers.
  final Color line;

  /// Field borders and stronger dividers.
  final Color lineStrong;

  /// Page background.
  final Color ground;

  /// Card and field background.
  final Color surface;

  final BondTone accent;
  final BondTone danger;
  final BondTone positive;
  final BondTone caution;
  final BondTone info;

  /// Text and icons drawn on a solid [BondTone.base] fill.
  final Color onFill;

  /// Drop shadow colour (already translucent).
  final Color shadow;

  /// Null uses the platform font.
  final String? fontFamily;
  final String? fontPackage;

  /// Colours for people, groups or series; index wraps. Never empty.
  final List<Color> personPalette;

  /// A fully transparent colour for widgets that need "no fill".
  static const Color transparent = Color(0x00000000);

  static const Color _white = Color(0xFFFFFFFF);
  static const Color _shadow = Color(0x1416181D);
  static const List<Color> _people = [
    Color(0xFF7285B4),
    Color(0xFF68936C),
    Color(0xFF9A8350),
    Color(0xFF9F769E),
    Color(0xFF49939D),
    Color(0xFF6A615F),
  ];

  /// Neutral greys plus one blue accent. For demos, tests and bare hosts.
  static const BondTokens fallback = BondTokens(
    ink: Color(0xFF1B1D21),
    body: Color(0xFF3F434A),
    muted: Color(0xFF6B7078),
    line: Color(0xFFE4E6EA),
    lineStrong: Color(0xFFCDD0D6),
    ground: Color(0xFFF6F7F9),
    surface: Color(0xFFFFFFFF),
    accent: BondTone(
      base: Color(0xFF2B63D9),
      press: Color(0xFF1E4DB0),
      wash: Color(0xFFEEF3FD),
      soft: Color(0xFFDCE6FA),
    ),
    danger: BondTone(
      base: Color(0xFFD92D20),
      press: Color(0xFFB42318),
      wash: Color(0xFFFEF3F2),
      soft: Color(0xFFFEE4E2),
    ),
    positive: BondTone(
      base: Color(0xFF17804A),
      press: Color(0xFF0F6638),
      wash: Color(0xFFEAF7EF),
      soft: Color(0xFFD3EFDF),
    ),
    caution: BondTone(
      base: Color(0xFFB86E00),
      press: Color(0xFF9A5B00),
      wash: Color(0xFFFFF5E5),
      soft: Color(0xFFFFE8C2),
    ),
    info: BondTone(
      base: Color(0xFF2459B8),
      press: Color(0xFF1B4491),
      wash: Color(0xFFEEF3FC),
      soft: Color(0xFFDAE5F8),
    ),
  );

  /// The tokens in scope, or [fallback] when no [BondTokens] extension is
  /// installed above [context].
  static BondTokens of(BuildContext context) =>
      Theme.of(context).extension<BondTokens>() ?? fallback;

  /// The colour family for [role].
  BondTone tone(BondToneRole role) => switch (role) {
        BondToneRole.accent => accent,
        BondToneRole.danger => danger,
        BondToneRole.positive => positive,
        BondToneRole.caution => caution,
        BondToneRole.info => info,
      };

  /// A grey family for neutral chips and banners.
  BondTone get neutral =>
      BondTone(base: body, press: ink, wash: ground, soft: line);

  /// Background, text and border for a pill or banner of [role]; a null role
  /// is the neutral grey.
  BondToneColors colorsFor(BondToneRole? role) {
    if (role == null) {
      return BondToneColors(background: ground, foreground: body, border: line);
    }
    final t = tone(role);
    return BondToneColors(
      background: t.wash,
      foreground: t.press,
      border: t.soft,
    );
  }

  /// Colour for person (or series) [n], 1-based; wraps after the palette.
  Color personColor(int n) =>
      personPalette[(n - 1) % personPalette.length];

  @override
  BondTokens copyWith({
    Color? ink,
    Color? body,
    Color? muted,
    Color? line,
    Color? lineStrong,
    Color? ground,
    Color? surface,
    BondTone? accent,
    BondTone? danger,
    BondTone? positive,
    BondTone? caution,
    BondTone? info,
    Color? onFill,
    Color? shadow,
    String? fontFamily,
    String? fontPackage,
    List<Color>? personPalette,
  }) =>
      BondTokens(
        ink: ink ?? this.ink,
        body: body ?? this.body,
        muted: muted ?? this.muted,
        line: line ?? this.line,
        lineStrong: lineStrong ?? this.lineStrong,
        ground: ground ?? this.ground,
        surface: surface ?? this.surface,
        accent: accent ?? this.accent,
        danger: danger ?? this.danger,
        positive: positive ?? this.positive,
        caution: caution ?? this.caution,
        info: info ?? this.info,
        onFill: onFill ?? this.onFill,
        shadow: shadow ?? this.shadow,
        fontFamily: fontFamily ?? this.fontFamily,
        fontPackage: fontPackage ?? this.fontPackage,
        personPalette: personPalette ?? this.personPalette,
      );

  @override
  BondTokens lerp(covariant ThemeExtension<BondTokens>? other, double t) {
    if (other is! BondTokens) return this;
    return BondTokens(
      ink: Color.lerp(ink, other.ink, t)!,
      body: Color.lerp(body, other.body, t)!,
      muted: Color.lerp(muted, other.muted, t)!,
      line: Color.lerp(line, other.line, t)!,
      lineStrong: Color.lerp(lineStrong, other.lineStrong, t)!,
      ground: Color.lerp(ground, other.ground, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      accent: BondTone.lerp(accent, other.accent, t),
      danger: BondTone.lerp(danger, other.danger, t),
      positive: BondTone.lerp(positive, other.positive, t),
      caution: BondTone.lerp(caution, other.caution, t),
      info: BondTone.lerp(info, other.info, t),
      onFill: Color.lerp(onFill, other.onFill, t)!,
      shadow: Color.lerp(shadow, other.shadow, t)!,
      fontFamily: t < 0.5 ? fontFamily : other.fontFamily,
      fontPackage: t < 0.5 ? fontPackage : other.fontPackage,
      personPalette: _lerpPalette(personPalette, other.personPalette, t),
    );
  }

  static List<Color> _lerpPalette(List<Color> a, List<Color> b, double t) {
    if (a.length != b.length) return t < 0.5 ? a : b;
    return [for (var i = 0; i < a.length; i++) Color.lerp(a[i], b[i], t)!];
  }
}
