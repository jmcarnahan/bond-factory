import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bond_test_support/bond_test_support.dart';

import 'support.dart';

const _event = EventCandidate(
  title: 'Site meeting',
  startDate: '2026-03-13',
  startTime: '10:00',
  location: 'Main yard',
  notes: 'Bring the plans',
  durationMinutes: 90,
  attendees: ['Dana', 'Lee'],
  confidence: 0.4,
  flags: ['low_confidence'],
);

const _task = TaskCandidate(
  title: 'Call Dana',
  dueDate: '2026-03-13',
  dueTime: '09:00',
  priority: TaskPriority.low,
  notes: 'Ask about the quote',
);

Future<void> _tap(WidgetTester t, Finder f) async {
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
}

Future<List<CaptureItem>> _pump(WidgetTester t, CaptureItem item) async {
  final got = <CaptureItem>[];
  await pumpAt(
    t,
    BondCaptureItemCard(item: item, onChanged: got.add, semanticsId: 'c'),
  );
  return got;
}

void _expectRich(EventCandidate e) {
  expect(e.location, 'Main yard');
  expect(e.notes, 'Bring the plans');
  expect(e.durationMinutes, 90);
  expect(e.attendees, ['Dana', 'Lee']);
  expect(e.confidence, 0.4);
  expect(e.flags, ['low_confidence']);
}

void main() {
  testWidgets('a rich event keeps location, notes, duration and attendees when the title is edited', (t) async {
    final sem = t.ensureSemantics();
    final got = await _pump(t, _event);
    await t.enterText(find.byType(TextField).first, 'Site meeting 2');
    await t.pump();
    final e = got.last as EventCandidate;
    expect(e.title, 'Site meeting 2');
    _expectRich(e);
    sem.dispose();
  });

  testWidgets('a rich event keeps the rich fields when the date or all-day changes', (t) async {
    final sem = t.ensureSemantics();
    final got = await _pump(t, _event);
    await _tap(t, find.bySemanticsIdentifier('c-due-date'));
    await _tap(t, find.bySemanticsIdentifier('c-due-date-day-2026-03-17'));
    var e = got.last as EventCandidate;
    expect(e.startDate, '2026-03-17');
    _expectRich(e);
    await _tap(t, find.bySemanticsIdentifier('c-all-day'));
    e = got.last as EventCandidate;
    expect((e.allDay, e.startTime), (true, null));
    expect((e.location, e.notes), ('Main yard', 'Bring the plans'));
    expect(e.attendees, ['Dana', 'Lee']);
    expect(e.durationMinutes, isNull, reason: 'an all-day event has no length in minutes');
    sem.dispose();
  });

  testWidgets('a rich task keeps its notes when the date or the priority changes', (t) async {
    final sem = t.ensureSemantics();
    final got = await _pump(t, _task);
    await _tap(t, find.bySemanticsIdentifier('c-due-date'));
    await _tap(t, find.bySemanticsIdentifier('c-due-date-day-2026-03-17'));
    var task = got.last as TaskCandidate;
    expect(task.dueDate, '2026-03-17');
    expect(task.notes, 'Ask about the quote');
    await _tap(t, find.text('High').first);
    task = got.last as TaskCandidate;
    expect(task.priority, TaskPriority.high);
    expect(task.notes, 'Ask about the quote');
    sem.dispose();
  });

  testWidgets('switching a task to an event carries the notes', (t) async {
    final toEvent = await _pump(t, _task);
    await _tap(t, find.text('Event'));
    final e = toEvent.last as EventCandidate;
    expect(e.notes, 'Ask about the quote');
    expect((e.startDate, e.startTime), ('2026-03-13', '09:00'));
  });

  testWidgets('switching an event to a task carries the notes', (t) async {
    final toTask = await _pump(t, _event);
    await _tap(t, find.text('Task'));
    final task = toTask.last as TaskCandidate;
    expect(task.notes, 'Bring the plans');
    expect((task.dueDate, task.dueTime), ('2026-03-13', '10:00'));
  });

  testWidgets('removing the time still clears it (copyWith does not keep the old one)', (t) async {
    final sem = t.ensureSemantics();
    final got = await _pump(t, _task);
    await _tap(t, find.bySemanticsIdentifier('c-due-time-remove'));
    final task = got.last as TaskCandidate;
    expect((task.dueDate, task.dueTime), ('2026-03-13', null));
    expect(task.notes, 'Ask about the quote');
    sem.dispose();
  });

  testWidgets('a custom shape reaches the card border', (t) async {
    final custom = BondTokens.fallback.copyWith(shape: const BondShape(r12: 3));
    setPhone(t);
    await pumpApp(
      t,
      const BondCaptureItemCard(item: _task, onChanged: _ignore),
      theme: BondTheme.build(custom),
    );
    final radii = t
        .widgetList<Container>(find.descendant(of: find.byType(BondCaptureItemCard), matching: find.byType(Container)))
        .map((c) => c.decoration)
        .whereType<BoxDecoration>()
        .map((d) => d.borderRadius);
    expect(radii, contains(BorderRadius.circular(3)));
  });
}

void _ignore(CaptureItem _) {}
