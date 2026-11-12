import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/src/primitives/bond_dashed_border.dart';
import 'package:bond_ui/src/primitives/bond_photo.dart';
import 'package:bond_ui/src/primitives/bond_pressable.dart';
import 'package:bond_ui/src/theme/theme.dart';
import 'package:bond_ui/src/tokens/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _custom = BondShape(r4: 1, r8: 2, r12: 3, r16: 5, r20: 7);

Future<void> _pump(WidgetTester t, Widget child, [BondShape? shape]) async {
  setPhone(t);
  await pumpApp(
    t,
    SingleChildScrollView(padding: BondSpace.all16, child: child),
    theme: BondTheme.build(shape == null ? BondTokens.fallback : BondTokens.fallback.copyWith(shape: shape)),
  );
}

BorderRadius? _pressableRadius(WidgetTester t) =>
    t.widget<Material>(find.descendant(of: find.byType(BondPressable), matching: find.byType(Material)).first).borderRadius
        as BorderRadius?;

BorderRadius? _photoRadius(WidgetTester t) => t.widget<ClipRRect>(find.descendant(of: find.byType(BondPhoto), matching: find.byType(ClipRRect))).borderRadius as BorderRadius?;

BorderRadiusGeometry? _dashedRadius(WidgetTester t) =>
    (t.widget<DecoratedBox>(find.descendant(of: find.byType(BondDashedBorder), matching: find.byType(DecoratedBox))).decoration as BoxDecoration).borderRadius;

void main() {
  group('BondPressable', () {
    const w = BondPressable(onTap: null, child: SizedBox(width: 40, height: 40));
    testWidgets('default is the old r8 value', (t) async {
      await _pump(t, w);
      expect(_pressableRadius(t), BondRadius.r8All);
    });
    testWidgets('a custom shape reaches it', (t) async {
      await _pump(t, w, _custom);
      expect(_pressableRadius(t), BorderRadius.circular(2));
    });
    testWidgets('an explicit radius still wins', (t) async {
      await _pump(t, const BondPressable(onTap: null, borderRadius: BorderRadius.all(Radius.circular(9)), child: SizedBox(width: 40, height: 40)), _custom);
      expect(_pressableRadius(t), BorderRadius.circular(9));
    });
  });

  group('BondPhoto', () {
    testWidgets('default is the old r12 value', (t) async {
      await _pump(t, const BondPhoto(url: null, width: 40, height: 40));
      expect(_photoRadius(t), BondRadius.r12All);
    });
    testWidgets('a custom shape reaches it', (t) async {
      await _pump(t, const BondPhoto(url: null, width: 40, height: 40), _custom);
      expect(_photoRadius(t), BorderRadius.circular(3));
    });
    testWidgets('an explicit radius still wins', (t) async {
      await _pump(t, BondPhoto(url: null, width: 40, height: 40, radius: BorderRadius.circular(9)), _custom);
      expect(_photoRadius(t), BorderRadius.circular(9));
    });
  });

  group('BondDashedBorder', () {
    const child = SizedBox(height: 30);
    testWidgets('default is the old r12 value', (t) async {
      await _pump(t, const BondDashedBorder(child: child));
      expect(_dashedRadius(t), BorderRadius.circular(BondRadius.r12));
    });
    testWidgets('a custom shape reaches it', (t) async {
      await _pump(t, const BondDashedBorder(child: child), _custom);
      expect(_dashedRadius(t), BorderRadius.circular(3));
    });
    testWidgets('an explicit radius still wins', (t) async {
      await _pump(t, const BondDashedBorder(radius: 9, child: child), _custom);
      expect(_dashedRadius(t), BorderRadius.circular(9));
    });
  });
}
