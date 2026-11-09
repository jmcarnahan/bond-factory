import 'package:bond_ui/src/theme/theme.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const f = BondTokens.fallback;
  const text = BondText(f);

  test('sizes and weights of the scale', () {
    expect(text.title.fontSize, BondText.title20);
    expect(text.heading.fontSize, BondText.heading28);
    expect(text.display.fontWeight, BondText.bold);
    expect(text.body.fontSize, BondText.base16);
    expect(text.small.fontSize, BondText.small14);
    expect(text.caption.fontSize, BondText.caption12);
  });

  test('colours come from the tokens', () {
    expect(text.body.color, f.body);
    expect(text.bodyStrong.color, f.ink);
    expect(text.label.color, f.muted);
    expect(text.eyebrow.color, f.muted);
    final custom = BondText(f.copyWith(ink: const Color(0xFF010203)));
    expect(custom.title.color, const Color(0xFF010203));
  });

  test('font family and package come from the tokens', () {
    expect(text.body.fontFamily, isNull);
    final custom =
        BondText(f.copyWith(fontFamily: 'Example', fontPackage: 'pkg'));
    expect(custom.body.fontFamily, 'packages/pkg/Example');
    expect(custom.heading.fontFamily, 'packages/pkg/Example');
  });

  test('tight styles track and lead tighter than running text', () {
    expect(text.heading.height, 1.2);
    expect(text.heading.letterSpacing, lessThan(0));
    expect(text.body.height, 1.5);
    expect(text.body.letterSpacing, 0);
  });

  test('mono ignores the token font', () {
    final custom = BondText(f.copyWith(fontFamily: 'Example'));
    expect(custom.mono.fontFamily, 'monospace');
    expect(custom.mono.fontFamilyFallback, isNotEmpty);
  });

  test('textTheme fills the Material slots', () {
    final tt = BondText.textTheme(f);
    expect(tt.titleLarge, isNotNull);
    expect(tt.bodyMedium!.fontSize, BondText.small14);
    expect(tt.labelLarge!.fontWeight, BondText.semibold);
  });

  testWidgets('BondTheme.build installs tokens and the text theme', (t) async {
    final theme = BondTheme.build(f);
    expect(theme.extension<BondTokens>(), same(f));
    expect(theme.colorScheme.primary, f.accent.base);
    expect(theme.scaffoldBackgroundColor, f.ground);
    expect(theme.textTheme.bodyLarge!.fontSize, BondText.base16);
    expect(BondTheme.build(f, brightness: Brightness.dark).brightness,
        Brightness.dark);

    late BondText got;
    await t.pumpWidget(BondScope(
      tokens: f.copyWith(ink: const Color(0xFF0A0B0C)),
      child: Builder(builder: (c) {
        got = BondText.of(c);
        return const SizedBox();
      }),
    ));
    expect(got.title.color, const Color(0xFF0A0B0C));
  });
}
