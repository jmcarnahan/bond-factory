import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the barrel exports tokens, theme, labels, semantics and primitives', () {
    // Tokens.
    expect(BondTokens.fallback.accent, isA<BondTone>());
    expect(BondSpace.s16, 16);
    expect(BondRadius.r12, 12);
    expect(BondLayout.forWidth(390).isPhone, isTrue);
    expect(BondToneRole.values, hasLength(5));
    expect(BondShadows.none, isEmpty);
    expect(const BondText(BondTokens.fallback).body.fontSize, BondText.base16);
    // Theme.
    expect(BondTheme.build(BondTokens.fallback), isNotNull);
    expect(const BondScope(child: SizedBox()), isNotNull);
    // Labels and semantics.
    expect(BondLabels.defaults.confirm, 'Confirm');
    expect(bondSemanticsOption('x', 'y'), 'x-y');
    // Primitives: one reference each so a dropped export fails to compile.
    final types = <Type>[
      BondActionRow, BondAvatar, BondBanner, BondButton, BondCard, BondChip,
      BondConfirm, BondDashedBorder, BondDateField, BondIconButton,
      BondInlineField, BondListRow, BondPhoto, BondPressable,
      BondSegmented<int>, BondSelect<int>, BondStatusChip, BondTextField,
      BondTimeField,
    ];
    expect(types.toSet(), hasLength(19));
  });
}
