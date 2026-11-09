import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const f = BondTokens.fallback;

  group('fallback', () {
    test('every colour slot is set', () {
      final colors = <Color>[
        f.ink, f.body, f.muted, f.line, f.lineStrong, f.ground, f.surface,
        f.onFill, f.shadow,
      ];
      for (final t in [f.accent, f.danger, f.positive, f.caution, f.info]) {
        colors.addAll([t.base, t.press, t.wash, t.soft]);
      }
      expect(colors.length, 29);
      // Text slots are opaque; washes are lighter than their base.
      expect(f.ink.a, 1);
      expect(f.surface, const Color(0xFFFFFFFF));
      expect(f.accent.wash.computeLuminance(),
          greaterThan(f.accent.base.computeLuminance()));
      expect(f.personPalette, isNotEmpty);
      expect(f.fontFamily, isNull);
    });
  });

  group('tone', () {
    test('maps every role to its slot', () {
      expect(f.tone(BondToneRole.accent), same(f.accent));
      expect(f.tone(BondToneRole.danger), same(f.danger));
      expect(f.tone(BondToneRole.positive), same(f.positive));
      expect(f.tone(BondToneRole.caution), same(f.caution));
      expect(f.tone(BondToneRole.info), same(f.info));
    });

    test('colorsFor: null is neutral, a role uses wash, press, soft', () {
      final n = f.colorsFor(null);
      expect(n.background, f.ground);
      expect(n.foreground, f.body);
      final d = f.colorsFor(BondToneRole.danger);
      expect(d.background, f.danger.wash);
      expect(d.foreground, f.danger.press);
      expect(d.border, f.danger.soft);
    });

    test('personColor is 1-based and wraps', () {
      expect(f.personColor(1), f.personPalette.first);
      expect(f.personColor(f.personPalette.length + 1), f.personPalette.first);
    });
  });

  group('copyWith and lerp', () {
    test('copyWith without arguments keeps every slot', () {
      final c = f.copyWith();
      expect(c.ink, f.ink);
      expect(c.accent, f.accent);
      expect(c.personPalette, f.personPalette);
    });

    test('copyWith replaces only what is named', () {
      final c = f.copyWith(
        ink: const Color(0xFF000000),
        accent: f.danger,
        fontFamily: 'Example',
        fontPackage: 'example_pkg',
      );
      expect(c.ink, const Color(0xFF000000));
      expect(c.accent, f.danger);
      expect(c.fontFamily, 'Example');
      expect(c.fontPackage, 'example_pkg');
      expect(c.body, f.body);
    });

    test('lerp round trips at the ends and blends in the middle', () {
      final other = f.copyWith(
        ink: const Color(0xFF000000),
        accent: f.danger,
        personPalette: const [Color(0xFF111111)],
      );
      expect(f.lerp(other, 0).ink, f.ink);
      expect(f.lerp(other, 1).ink, other.ink);
      expect(f.lerp(other, 1).accent, other.accent);
      expect(f.lerp(other, 0).personPalette, f.personPalette);
      expect(f.lerp(other, 1).personPalette, other.personPalette);
      final mid = f.lerp(other, 0.5);
      expect(mid.ink, Color.lerp(f.ink, other.ink, 0.5));
    });

    test('lerp with a foreign extension returns this', () {
      expect(f.lerp(null, 0.5), same(f));
    });

    test('BondTone equality and lerp', () {
      expect(f.accent, f.accent.copyWith());
      expect(f.accent == f.danger, isFalse);
      expect(BondTone.lerp(f.accent, f.danger, 1), f.danger);
    });
  });

  group('BondTokens.of', () {
    testWidgets('falls back when no extension is installed', (t) async {
      late BondTokens got;
      await t.pumpWidget(MaterialApp(
        home: Builder(builder: (c) {
          got = BondTokens.of(c);
          return const SizedBox();
        }),
      ));
      expect(got, same(BondTokens.fallback));
    });

    testWidgets('reads the installed extension', (t) async {
      final custom = f.copyWith(ink: const Color(0xFF123456));
      late BondTokens got;
      await t.pumpWidget(MaterialApp(
        theme: ThemeData(extensions: [custom]),
        home: Builder(builder: (c) {
          got = BondTokens.of(c);
          return const SizedBox();
        }),
      ));
      expect(got.ink, const Color(0xFF123456));
    });
  });

  group('constants', () {
    test('space and radius scale', () {
      expect(BondSpace.s4, 4);
      expect(BondSpace.s64, 64);
      expect(BondSpace.all16, const EdgeInsets.all(16));
      expect(BondSpace.page.horizontal, 64);
      expect(BondSpace.pageMobile.horizontal, 32);
      expect(BondRadius.r12All, BorderRadius.circular(12));
      expect(BondRadius.pill, 999);
    });

    test('layout breakpoints', () {
      expect(BondLayout.forWidth(390).size, BondSize.phone);
      expect(BondLayout.forWidth(719).isPhone, isTrue);
      expect(BondLayout.forWidth(720).isTablet, isTrue);
      expect(BondLayout.forWidth(1099).isTablet, isTrue);
      expect(BondLayout.forWidth(1100).isDesktop, isTrue);
      expect(BondLayout.forWidth(390).pagePadding, BondSpace.pageMobile);
      expect(BondLayout.forWidth(1280).pagePadding, BondSpace.page);
    });

    testWidgets('BondLayout.of reads the window width', (t) async {
      t.view.physicalSize = const Size(390, 844);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);
      late BondLayout got;
      await t.pumpWidget(MaterialApp(
        home: Builder(builder: (c) {
          got = BondLayout.of(c);
          return const SizedBox();
        }),
      ));
      expect(got.isPhone, isTrue);
    });
  });
}
