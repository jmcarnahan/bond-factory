import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/primitives/bond_banner.dart';
import 'package:bond_ui/src/primitives/bond_button.dart';
import 'package:bond_ui/src/primitives/bond_card.dart';
import 'package:bond_ui/src/primitives/bond_chip.dart';
import 'package:bond_ui/src/primitives/bond_text_field.dart';
import 'package:bond_ui/src/theme/theme.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _custom = BondShape(r4: 1, r8: 2, r12: 3, r16: 5, r20: 7);

Future<void> _pump(WidgetTester t, Widget child, BondShape shape) async {
  setPhone(t);
  await pumpApp(
    t,
    SingleChildScrollView(padding: BondSpace.all16, child: child),
    theme: BondTheme.build(BondTokens.fallback.copyWith(shape: shape)),
  );
}

Iterable<BorderRadiusGeometry?> _radii(WidgetTester t, Finder under) => t
    .widgetList<Container>(
      find.descendant(of: under, matching: find.byType(Container)),
    )
    .map((c) => c.decoration)
    .whereType<BoxDecoration>()
    .map((d) => d.borderRadius);

void main() {
  test('default shape equals the old constants', () {
    const s = BondShape();
    expect(
      [s.r4, s.r8, s.r12, s.r16, s.r20],
      [
        BondRadius.r4,
        BondRadius.r8,
        BondRadius.r12,
        BondRadius.r16,
        BondRadius.r20,
      ],
    );
    expect(s.r12All, BondRadius.r12All);
    expect(s.r16All, BondRadius.r16All);
    expect(BondTokens.fallback.shape, const BondShape());
    expect(const BondShape().copyWith(r8: 2), isNot(const BondShape()));
    expect(BondShape.lerp(const BondShape(), _custom, 1), _custom);
    expect(BondTokens.fallback.copyWith(shape: _custom).shape, _custom);
  });

  testWidgets('a custom shape reaches a button', (t) async {
    await _pump(t, BondButton(label: 'Go', onPressed: () {}), _custom);
    expect(
      _radii(t, find.byType(BondButton)),
      contains(BorderRadius.circular(3)),
    );
  });

  testWidgets('a custom shape reaches a banner', (t) async {
    await _pump(t, const BondBanner(title: 'Hi'), _custom);
    expect(
      _radii(t, find.byType(BondBanner)),
      contains(BorderRadius.circular(3)),
    );
  });

  testWidgets('a custom shape reaches a card', (t) async {
    await _pump(t, const BondCard(child: Text('x')), _custom);
    expect(find.byType(BondCard), findsOneWidget);
    final radii = t
        .widgetList<Material>(
          find.descendant(
            of: find.byType(BondCard),
            matching: find.byType(Material),
          ),
        )
        .map((m) => m.borderRadius)
        .toList();
    final boxes = _radii(t, find.byType(BondCard)).toList();
    expect([...radii, ...boxes], contains(BorderRadius.circular(5)));
  });

  testWidgets('a custom shape reaches a field', (t) async {
    await _pump(t, const BondTextField(label: 'Name'), _custom);
    final ctx = t.element(find.byType(BondTextField));
    final border =
        Theme.of(ctx).inputDecorationTheme.enabledBorder as OutlineInputBorder;
    expect(border.borderRadius, BorderRadius.circular(3));
    final focus =
        bondFocusedBorder(const Color(0xFF000000), _custom)
            as OutlineInputBorder;
    expect(focus.borderRadius, BorderRadius.circular(3));
  });

  testWidgets('a chip stays a pill whatever the shape', (t) async {
    await _pump(t, const BondChip(label: 'Tag'), _custom);
    expect(_radii(t, find.byType(BondChip)), contains(BondRadius.pillAll));
  });
}
