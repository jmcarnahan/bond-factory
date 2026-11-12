import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

const _task = Task(id: 't1', title: 'Send the invoice', dueDate: '2026-03-12');

void main() {
  for (final phone in [false, true]) {
    testWidgets('stage text, title and the three actions (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      final got = <NoticeAction>[];
      await pumpAt(
        t,
        BondStageBanner(task: _task, stage: TaskStage.due, onAction: got.add, semanticsPrefix: 'b'),
        phone: phone,
      );
      expect(find.text('Due now'), findsOneWidget);
      expect(find.text('Send the invoice'), findsOneWidget);
      expect(find.text('Last reminder'), findsNothing);
      for (final (label, action) in [
        ('Done', NoticeAction.done),
        ('Snooze', NoticeAction.snooze),
        ('Cancel task', NoticeAction.cancel),
      ]) {
        await t.tap(find.text(label));
        expect(got.last, action);
      }
      expect(find.bySemanticsIdentifier('b.banner'), findsOneWidget);
      expect(find.bySemanticsIdentifier('b.banner-snooze'), findsOneWidget);
      await expectNoOverlays(t);
      expect(find.byType(MaterialBanner), findsNothing);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('an upcoming task (due far ahead) and stage none draw nothing', (t) async {
    await pumpAt(t, BondStageBanner(task: _task, stage: TaskStage.upcoming, onAction: (_) {}));
    expect(find.text('Due soon'), findsNothing);
    expect(find.text('Send the invoice'), findsNothing);
    expect(find.text('Done'), findsNothing);
  });

  testWidgets('each stage has its own words', (t) async {
    for (final (stage, text) in [
      (TaskStage.close, 'Due soon'),
      (TaskStage.due, 'Due now'),
      (TaskStage.past, 'Overdue'),
    ]) {
      await pumpAt(t, BondStageBanner(task: _task, stage: stage, onAction: (_) {}));
      expect(find.text(text), findsOneWidget, reason: '$stage');
    }
  });

  testWidgets('last adds the last-reminder line', (t) async {
    await pumpAt(t, BondStageBanner(task: _task, stage: TaskStage.past, last: true, onAction: (_) {}));
    expect(find.text('Last reminder'), findsOneWidget);
  });

  testWidgets('only the given actions show', (t) async {
    await pumpAt(
      t,
      BondStageBanner(task: _task, stage: TaskStage.due, actions: const [NoticeAction.done], onAction: (_) {}),
    );
    expect(find.text('Done'), findsOneWidget);
    expect(find.text('Snooze'), findsNothing);
    expect(find.text('Cancel task'), findsNothing);
  });

  testWidgets('stage none draws nothing', (t) async {
    await pumpAt(t, BondStageBanner(task: _task, stage: TaskStage.none, onAction: (_) {}));
    expect(find.text('Send the invoice'), findsNothing);
  });
}
