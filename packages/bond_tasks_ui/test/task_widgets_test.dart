import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final Task _open = Task(
  id: 't1',
  title: 'Send the estimate',
  dueDate: '2026-03-12',
  dueTime: '09:30',
  assignedUserId: 'u2',
  assigneeName: 'Viewer User',
  checklist: [
    const ChecklistItem(id: 'a', text: 'Confirm scope'),
    ChecklistItem(id: 'b', text: 'Attach estimate', doneAt: DateTime.utc(2026, 3, 10)),
  ],
);

const Task _late = Task(id: 't2', title: 'Call back', dueDate: '2026-03-01', overdue: true);
const Task _undated = Task(id: 't3', title: 'Someday');
const Task _done = Task(id: 't4', title: 'Filed', dueDate: '2026-03-12', status: TaskStatus.done);

void main() {
  group('BondTaskRow', () {
    testWidgets('shows title, due, assignee, progress and fires callbacks', (t) async {
      var tapped = 0;
      var completed = 0;
      await pumpAt(t, BondTaskRow(task: _open, onTap: () => tapped++, onComplete: () => completed++));
      expect(find.text('Send the estimate'), findsOneWidget);
      expect(find.textContaining('Mar 12, 9:30 AM'), findsOneWidget);
      expect(find.textContaining('Checklist 1 of 2'), findsOneWidget);
      expect(find.text('Viewer User'), findsOneWidget);
      await t.tap(find.text('Send the estimate'));
      await t.tap(find.byIcon(Icons.radio_button_unchecked));
      expect((tapped, completed), (1, 1));
    });

    testWidgets('overdue and done rows say so', (t) async {
      await pumpAt(t, const Column(children: [BondTaskRow(task: _late), BondTaskRow(task: _done)]));
      expect(find.text('Overdue'), findsOneWidget);
      expect(find.text('Done'), findsOneWidget);
      expect(find.byIcon(Icons.check_circle), findsOneWidget);
    });

    testWidgets('no overlays at 1280 and 390', (t) async {
      await expectCleanAtBothWidths(t, () => BondTaskRow(task: _open, onTap: () {}, onComplete: () {}));
    });
  });

  group('BondTaskList', () {
    testWidgets('groups into sections in order', (t) async {
      await pumpAt(t, BondTaskList(tasks: [_undated, _done, _open, _late], today: kToday));
      final titles = ['Overdue (1)', 'Today (1)', 'No date (1)', 'Done (1)'];
      for (final s in titles) {
        expect(find.text(s), findsOneWidget);
      }
      expect(find.textContaining('Upcoming'), findsNothing);
      final ys = [for (final s in titles) t.getTopLeft(find.text(s)).dy];
      expect(ys, orderedEquals([...ys]..sort()));
    });

    testWidgets('empty, loading and error states', (t) async {
      await pumpAt(t, BondTaskList(tasks: const [], today: kToday));
      expect(find.text('No tasks'), findsOneWidget);
      await pumpAt(t, BondTaskList(tasks: null, today: kToday));
      expect(find.text('Loading tasks'), findsOneWidget);
      var retried = 0;
      await pumpAt(t, BondTaskList(tasks: null, today: kToday, error: 'Tasks could not be loaded.', onRetry: () => retried++));
      expect(find.text('Tasks could not be loaded.'), findsOneWidget);
      await t.tap(find.text('Retry'));
      expect(retried, 1);
    });

    testWidgets('rowExtra and complete callback', (t) async {
      Task? completed;
      await pumpAt(
        t,
        BondTaskList(
          tasks: [_open],
          today: kToday,
          onComplete: (k) => completed = k,
          rowExtra: (_, k) => Text('extra-${k.id}'),
        ),
      );
      expect(find.text('extra-t1'), findsOneWidget);
      await t.tap(find.byIcon(Icons.radio_button_unchecked));
      expect(completed?.id, 't1');
    });

    testWidgets('no overlays at 1280 and 390', (t) async {
      await expectCleanAtBothWidths(t, () => BondTaskList(tasks: [_open, _late, _undated, _done], today: kToday));
    });
  });

  group('BondChecklist', () {
    testWidgets('tick fires with the line and the new state', (t) async {
      ChecklistItem? item;
      bool? done;
      await pumpAt(t, BondChecklist(items: _open.checklist, onToggle: (i, d) {
        item = i;
        done = d;
      }));
      await t.tap(find.text('Confirm scope'));
      expect((item?.id, done), ('a', true));
      await t.tap(find.text('Attach estimate'));
      expect((item?.id, done), ('b', false));
    });

    testWidgets('no overlays at 1280 and 390', (t) async {
      await expectCleanAtBothWidths(t, () => BondChecklist(items: _open.checklist, onToggle: (_, _) {}, onRemove: (_) {}));
    });
  });

  group('BondTaskQuickAdd', () {
    testWidgets('enter submits the trimmed title and clears the box', (t) async {
      final got = <String>[];
      await pumpAt(t, BondTaskQuickAdd(onSubmit: got.add));
      await t.enterText(find.byType(TextField), '  Buy tape ');
      await t.testTextInput.receiveAction(TextInputAction.done);
      await t.pump();
      expect(got, ['Buy tape']);
      expect(t.widget<TextField>(find.byType(TextField)).controller!.text, '');
    });

    testWidgets('an empty line does nothing; the button submits', (t) async {
      final got = <String>[];
      await pumpAt(t, BondTaskQuickAdd(onSubmit: got.add));
      await t.tap(find.text('Add'));
      expect(got, isEmpty);
      await t.enterText(find.byType(TextField), 'One');
      await t.tap(find.text('Add'));
      expect(got, ['One']);
    });

    testWidgets('no overlays at 1280 and 390', (t) async {
      await expectCleanAtBothWidths(t, () => BondTaskQuickAdd(onSubmit: (_) {}));
    });
  });

  group('BondTaskSummaryCard', () {
    testWidgets('shows the four counts', (t) async {
      await pumpAt(t, const BondTaskSummaryCard(summary: TaskSummary(open: 7, overdue: 2, dueToday: 3, noDate: 1)));
      for (final s in ['7', '2', '3', '1', 'Open', 'Overdue', 'Due today', 'No date']) {
        expect(find.text(s), findsOneWidget, reason: s);
      }
    });

    testWidgets('no overlays at 1280 and 390', (t) async {
      await expectCleanAtBothWidths(t, () => const BondTaskSummaryCard(summary: TaskSummary(open: 1)));
    });
  });

  group('BondTaskDeleteControl', () {
    testWidgets('two steps: delete then confirm', (t) async {
      var deleted = 0;
      await pumpAt(t, BondTaskDeleteControl(taskId: 't1', onDelete: () => deleted++));
      await t.tap(find.byIcon(Icons.delete_outline));
      await t.pump();
      expect(deleted, 0);
      await t.tap(find.text('Confirm'));
      await t.pump();
      expect(deleted, 1);
      await t.pump(const Duration(seconds: 11));
    });

    testWidgets('cancel leaves the task alone', (t) async {
      var deleted = 0;
      await pumpAt(t, BondTaskDeleteControl(taskId: 't1', onDelete: () => deleted++));
      await t.tap(find.byIcon(Icons.delete_outline));
      await t.pump();
      await t.tap(find.text('Cancel'));
      await t.pump();
      expect(deleted, 0);
      expect(find.byIcon(Icons.delete_outline), findsOneWidget);
    });

    testWidgets('no overlays at 1280 and 390, armed or not', (t) async {
      await expectCleanAtBothWidths(t, () => BondTaskDeleteControl(taskId: 't1', onDelete: () {}));
      await t.tap(find.byIcon(Icons.delete_outline));
      await t.pump();
      await expectCleanAtBothWidths(t, () => BondTaskDeleteControl(taskId: 't2', onDelete: () {}));
    });
  });
}
