import 'package:bond_ui/src/primitives/bond_button.dart';
import 'package:bond_ui/src/primitives/bond_confirm.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'host.dart';

void main() {
  Widget confirm({
    required List<String> log,
    Object identity = 1,
    Duration? undoWindow,
    Duration? armTimeout = const Duration(seconds: 10),
    bool immediate = false,
    bool stacked = false,
  }) =>
      BondConfirm(
        identity: identity,
        undoWindow: undoWindow,
        armTimeout: armTimeout,
        immediate: immediate,
        stacked: stacked,
        semanticsId: 'del',
        onConfirm: () => log.add('confirm'),
        onCancel: () => log.add('cancel'),
        onUndo: () => log.add('undo'),
        trigger: (arm) => BondButton(label: 'Delete', onPressed: arm),
      );

  testWidgets('two steps: arm, then confirm; ids on both buttons', (t) async {
    final sem = t.ensureSemantics();
    final log = <String>[];
    await pumpBond(t, confirm(log: log));
    expect(find.text('Delete'), findsOneWidget);
    expect(find.text('Confirm'), findsNothing);

    await t.tap(find.text('Delete'));
    await t.pump();
    expect(log, isEmpty);
    expect(find.text('Delete'), findsNothing);
    expect(find.text('Confirm'), findsOneWidget);
    expect(find.text('Cancel'), findsOneWidget);
    expect(find.bySemanticsIdentifier('del-confirm'), findsOneWidget);
    expect(find.bySemanticsIdentifier('del-cancel'), findsOneWidget);
    await expectNoOverlays(t);

    await t.tap(find.text('Confirm'));
    await t.pump();
    expect(log, ['confirm']);
    expect(find.text('Delete'), findsOneWidget);
    await expectNoOverlays(t);
    sem.dispose();
  });

  testWidgets('cancel disarms and calls onCancel', (t) async {
    final log = <String>[];
    await pumpBond(t, confirm(log: log));
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.tap(find.text('Cancel'));
    await t.pump();
    expect(log, ['cancel']);
    expect(find.text('Delete'), findsOneWidget);
  });

  testWidgets('the armed state times out by itself', (t) async {
    final log = <String>[];
    await pumpBond(t, confirm(log: log));
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.pump(const Duration(seconds: 9));
    expect(find.text('Confirm'), findsOneWidget);
    await t.pump(const Duration(seconds: 2));
    expect(find.text('Confirm'), findsNothing);
    expect(find.text('Delete'), findsOneWidget);
    expect(log, ['cancel']);
  });

  testWidgets('a null armTimeout waits until the person decides', (t) async {
    final log = <String>[];
    await pumpBond(t, confirm(log: log, armTimeout: null));
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.pump(const Duration(minutes: 5));
    expect(find.text('Confirm'), findsOneWidget);
    expect(log, isEmpty);
  });

  testWidgets('undo window: Sent . Undo shows, undo runs onUndo, then it ends',
      (t) async {
    final sem = t.ensureSemantics();
    final log = <String>[];
    await pumpBond(
      t,
      confirm(log: log, undoWindow: const Duration(seconds: 5)),
    );
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.tap(find.text('Confirm'));
    await t.pump();
    expect(log, ['confirm']);
    expect(find.text('Sent'), findsOneWidget);
    expect(find.bySemanticsIdentifier('del-undo'), findsOneWidget);
    await t.tap(find.text('Undo'));
    await t.pump();
    expect(log, ['confirm', 'undo']);
    expect(find.text('Delete'), findsOneWidget);
    sem.dispose();
  });

  testWidgets('the undo window ends by itself', (t) async {
    final log = <String>[];
    await pumpBond(
      t,
      confirm(log: log, undoWindow: const Duration(seconds: 5)),
    );
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.tap(find.text('Confirm'));
    await t.pump();
    await t.pump(const Duration(seconds: 6));
    expect(find.text('Sent'), findsNothing);
    expect(find.text('Delete'), findsOneWidget);
  });

  testWidgets('immediate confirms in one tap and offers undo', (t) async {
    final log = <String>[];
    await pumpBond(
      t,
      confirm(
        log: log,
        immediate: true,
        undoWindow: const Duration(seconds: 5),
      ),
    );
    await t.tap(find.text('Delete'));
    await t.pump();
    expect(log, ['confirm']);
    expect(find.text('Confirm'), findsNothing);
    expect(find.text('Sent'), findsOneWidget);
  });

  testWidgets('stacked + undoWindow: the done row is not stacked', (t) async {
    final log = <String>[];
    await pumpBond(
      t,
      confirm(
        log: log,
        stacked: true,
        undoWindow: const Duration(seconds: 5),
      ),
    );
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.tap(find.text('Confirm'));
    await t.pump();
    // Sent and Undo sit side by side on one line.
    expect(t.getTopLeft(find.text('Sent')).dy,
        t.getTopLeft(find.text('Undo')).dy);
    expect(find.text('·'), findsOneWidget);
  });

  testWidgets('a throwing onCancel after armTimeout leaves the phase idle',
      (t) async {
    await pumpBond(
      t,
      BondConfirm(
        identity: 1,
        armTimeout: const Duration(seconds: 2),
        onConfirm: () {},
        onCancel: () => throw StateError('boom'),
        trigger: (arm) => BondButton(label: 'Delete', onPressed: arm),
      ),
    );
    await t.tap(find.text('Delete'));
    await t.pump();
    await t.pump(const Duration(seconds: 3));
    expect(find.text('Delete'), findsOneWidget);
    expect(find.text('Confirm'), findsNothing);
    expect(t.takeException(), isA<StateError>());
  });

  testWidgets('a new identity resets the armed state and cancels', (t) async {
    final log = <String>[];
    await pumpBond(t, confirm(log: log, identity: 1));
    await t.tap(find.text('Delete'));
    await t.pump();
    await pumpBond(t, confirm(log: log, identity: 2));
    await t.pump();
    expect(log, ['cancel']);
    expect(find.text('Delete'), findsOneWidget);
  });

  testWidgets('stacked and narrow layouts do not overflow at 390', (t) async {
    final log = <String>[];
    await pumpBond(
      t,
      Column(children: [
        confirm(log: log, stacked: true),
        SizedBox(width: 120, child: confirm(log: log)),
      ]),
    );
    await t.tap(find.text('Delete').first);
    await t.tap(find.text('Delete').last);
    await t.pump();
    expect(t.takeException(), isNull);
    expect(find.text('Confirm'), findsNWidgets(2));
  });
}
