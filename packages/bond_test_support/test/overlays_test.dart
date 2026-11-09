import 'dart:async';

import 'package:bond_test_support/bond_test_support.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('a plain page has no overlays', (t) async {
    await pumpApp(t, const Text('hello'));
    await expectNoOverlays(t);
  });

  testWidgets('an open dialog is detected', (t) async {
    late BuildContext ctx;
    await pumpApp(t, Builder(builder: (c) {
      ctx = c;
      return const Text('page');
    }));
    unawaited(showDialog<void>(context: ctx, builder: (_) => const AlertDialog(title: Text('hi'))));
    await t.pumpAndSettle();
    await expectLater(expectNoOverlays(t), throwsA(isA<TestFailure>()));
  });

  testWidgets('a bottom sheet is detected', (t) async {
    late BuildContext ctx;
    await pumpApp(t, Builder(builder: (c) {
      ctx = c;
      return const Text('page');
    }));
    unawaited(showModalBottomSheet<void>(context: ctx, builder: (_) => const SizedBox(height: 80)));
    await t.pumpAndSettle();
    await expectLater(expectNoOverlays(t), throwsA(isA<TestFailure>()));
  });

  testWidgets('a snack bar is detected', (t) async {
    late BuildContext ctx;
    await pumpApp(t, Builder(builder: (c) {
      ctx = c;
      return const Text('page');
    }));
    ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(content: Text('x')));
    await t.pump();
    await expectLater(expectNoOverlays(t), throwsA(isA<TestFailure>()));
  });

  testWidgets('a popup menu button is detected', (t) async {
    await pumpApp(
      t,
      PopupMenuButton<int>(itemBuilder: (_) => const [PopupMenuItem(value: 1, child: Text('one'))]),
    );
    await expectLater(expectNoOverlays(t), throwsA(isA<TestFailure>()));
  });

  testWidgets('a shown tooltip is detected', (t) async {
    await pumpApp(t, const Tooltip(message: 'tip', triggerMode: TooltipTriggerMode.manual, child: Text('x')));
    await expectNoOverlays(t);
    final tip = t.state<TooltipState>(find.byType(Tooltip));
    tip.ensureTooltipVisible();
    await t.pump();
    await expectLater(expectNoOverlays(t), throwsA(isA<TestFailure>()));
  });
}
