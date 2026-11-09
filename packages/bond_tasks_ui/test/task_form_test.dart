import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_test_support/bond_test_support.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

const List<TaskAssignee> _people = [TaskAssignee('u1', 'Demo User'), TaskAssignee('u2', 'Viewer User')];

Future<void> _tapText(WidgetTester t, String text) async {
  final f = find.text(text);
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
}

void main() {
  testWidgets('empty title shows the message inline and emits nothing', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(t, BondTaskForm(today: kToday, onSubmit: got.add));
    expect(find.text('Enter a title.'), findsNothing);
    await _tapText(t, 'Save task');
    expect(find.text('Enter a title.'), findsOneWidget);
    expect(got, isEmpty);
    await expectNoOverlays(t);
  });

  testWidgets('a time without a date shows its message and blocks save', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(
        today: kToday,
        onSubmit: got.add,
        initial: const Task(id: 'x', title: 'T', dueTime: '09:30'),
      ),
    );
    expect(find.text('Pick a date to set a time.'), findsOneWidget);
    await _tapText(t, 'Save task');
    expect(got, isEmpty);
  });

  testWidgets('a valid form emits a TaskDraft', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(
        today: kToday,
        onSubmit: got.add,
        assignees: _people,
        initial: const Task(id: 'x', title: 'Old', dueDate: '2026-03-12', dueTime: '09:30', mirrorEnabled: true),
      ),
    );
    await t.enterText(find.byType(BondTextField).first, '  New title ');
    await _tapText(t, 'Save task');
    expect(got, hasLength(1));
    final d = got.single;
    expect(d.toJson()['title'], 'New title');
    expect(d.dueDate, '2026-03-12');
    expect(d.dueTime, '09:30');
    expect(d.remindMinutesBefore, kRemindNone);
    expect(d.mirrorEnabled, isTrue);
    expect(d.validate(), isEmpty);
  });

  testWidgets('reminder and mirror choices land in the draft', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(today: kToday, onSubmit: got.add, initial: const Task(id: 'x', title: 'T')),
    );
    await _tapText(t, '1 hour before');
    await _tapText(t, 'Add to my calendar');
    await _tapText(t, 'Save task');
    expect(got.single.remindMinutesBefore, 60);
    expect(got.single.mirrorEnabled, isFalse);
  });

  testWidgets('a title over 255 characters shows the message at once and blocks save', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(t, BondTaskForm(today: kToday, onSubmit: got.add));
    await t.enterText(find.byType(BondTextField).first, 'a' * 256);
    await t.pump();
    expect(find.text('Use 255 characters or fewer.'), findsOneWidget);
    await _tapText(t, 'Save task');
    expect(got, isEmpty);
    await t.enterText(find.byType(BondTextField).first, 'a' * 255);
    await t.pump();
    expect(find.text('Use 255 characters or fewer.'), findsNothing);
    await _tapText(t, 'Save task');
    expect(got, hasLength(1));
  });

  testWidgets('an unreadable date is kept, flagged inline and sent back unchanged', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(
        today: kToday,
        onSubmit: got.add,
        initial: const Task(id: 'x', title: 'T', dueDate: '2026-13-45', dueTime: 'soon'),
      ),
    );
    expect(find.text('Unrecognised date: 2026-13-45'), findsOneWidget);
    expect(find.text('Unrecognised time: soon'), findsOneWidget);
    await _tapText(t, 'Save task');
    expect(got.single.dueDate, '2026-13-45');
    expect(got.single.dueTime, 'soon');
  });

  testWidgets('choosing a time replaces an unreadable one', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(
        today: kToday,
        onSubmit: got.add,
        initial: const Task(id: 'x', title: 'T', dueDate: '2026-03-12', dueTime: 'soon'),
      ),
    );
    await _tapText(t, 'Add a time');
    expect(find.textContaining('Unrecognised time'), findsNothing);
    await _tapText(t, 'Save task');
    expect(got.single.dueTime, '09:00');
  });

  testWidgets('the 1 minute reminder lands in the draft', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(today: kToday, onSubmit: got.add, initial: const Task(id: 'x', title: 'T')),
    );
    await _tapText(t, '1 minute before');
    await _tapText(t, 'Save task');
    expect(got.single.remindMinutesBefore, 1);
    expect(got.single.toJson()['remind_minutes_before'], 1);
  });

  testWidgets('assignee choice lands in the draft', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(today: kToday, onSubmit: got.add, assignees: _people, initial: const Task(id: 'x', title: 'T')),
    );
    await _tapText(t, 'Unassigned');
    await _tapText(t, 'Viewer User');
    await _tapText(t, 'Save task');
    expect(got.single.assignedUserId, 'u2');
  });

  testWidgets('checklist: add by enter, tick and remove', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(today: kToday, onSubmit: got.add, initial: const Task(id: 'x', title: 'T')),
    );
    final box = find.widgetWithText(BondTextField, '').last;
    await t.ensureVisible(box);
    await t.enterText(box, 'First');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pump();
    expect(find.text('First'), findsOneWidget);
    await _tapText(t, 'First');
    await _tapText(t, 'Save task');
    expect(got.single.checklist, hasLength(1));
    expect(got.single.checklist.single.text, 'First');
    expect(got.single.checklist.single.done, isTrue);
  });

  testWidgets('checklist remove button drops the line', (t) async {
    final got = <TaskDraft>[];
    await pumpAt(
      t,
      BondTaskForm(
        today: kToday,
        onSubmit: got.add,
        initial: const Task(id: 'x', title: 'T', checklist: [ChecklistItem(id: 'a', text: 'Gone')]),
      ),
    );
    await t.ensureVisible(find.byIcon(Icons.close));
    await t.tap(find.byIcon(Icons.close));
    await t.pump();
    expect(find.text('Gone'), findsNothing);
    await _tapText(t, 'Save task');
    expect(got.single.checklist, isEmpty);
  });

  testWidgets('semantics ids follow the prefix', (t) async {
    final handle = t.ensureSemantics();
    await pumpAt(t, BondTaskForm(today: kToday, onSubmit: (_) {}, assignees: _people, semanticsPrefix: 'sdk.tasks'));
    for (final id in ['title', 'notes', 'due-date', 'assignee', 'checklist-add', 'reminder-60', 'mirror', 'save']) {
      expect(
        find.byWidgetPredicate((w) => w is Semantics && w.properties.identifier == 'sdk.tasks.form-$id'),
        findsWidgets,
        reason: id,
      );
    }
    handle.dispose();
  });

  testWidgets('no overlays at 1280 and 390', (t) async {
    await expectCleanAtBothWidths(
      t,
      () => BondTaskForm(
        today: kToday,
        onSubmit: (_) {},
        onCancel: () {},
        assignees: _people,
        initial: const Task(
          id: 'x',
          title: 'T',
          dueDate: '2026-03-12',
          dueTime: '09:30',
          checklist: [ChecklistItem(id: 'a', text: 'One')],
        ),
      ),
    );
  });
}
