import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final DateTime _now = DateTime(2026, 3, 12, 12);

const _dana = LinkOption(id: 'c1', label: 'Dana Fox');
const _dan = LinkOption(id: 'c2', label: 'Dan Fowler');

List<CaptureItem> _items() => const [
      TaskCandidate(
        title: 'Call Dana about the quote',
        dueDate: '2026-03-13',
        dueTime: '09:00',
        priority: TaskPriority.high,
        links: [
          LinkCandidate(text: 'Dana', candidates: [_dana, _dan]),
        ],
      ),
      EventCandidate(title: 'Site visit', startDate: '2026-03-10', startTime: '10:00'),
      TaskCandidate(title: 'Order tiles', dueDate: '2026-03-14', dueDefaulted: true, flags: ['low_confidence']),
    ];

class _Search implements LinkSearch {
  @override
  Future<List<TaskLink>> search(String kind, String query) async =>
      [TaskLink(kind: kind, id: 'c9', label: 'Found $query')];
}

Future<void> _tap(WidgetTester t, Finder f) async {
  await t.ensureVisible(f);
  await t.tap(f);
  await t.pump();
}

void main() {
  for (final phone in [false, true]) {
    testWidgets('one card per item with marks (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      await pumpAt(
        t,
        BondCaptureReview(items: _items(), now: _now, onAccept: (_) {}, onDiscard: () {}, semanticsPrefix: 'c'),
        phone: phone,
      );
      expect(find.byType(BondCaptureItemCard), findsNWidgets(3));
      expect(find.text('Missed'), findsOneWidget, reason: 'only the past event');
      expect(find.text('Check this one'), findsOneWidget, reason: 'low confidence flag');
      expect(find.text('Date guessed'), findsOneWidget);
      expect(find.text('High'), findsWidgets);
      expect(find.text('Fri, Mar 13, 2026'), findsOneWidget, reason: 'the first item date, in its field');
      expect(find.bySemanticsIdentifier('c.review-accept'), findsOneWidget);
      expect(find.bySemanticsIdentifier('c.review-item-1-title'), findsOneWidget);
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('a past task is not "missed": only events are', (t) async {
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [TaskCandidate(title: 'Old', dueDate: '2026-03-01')],
        now: _now,
        onAccept: (_) {},
        onDiscard: () {},
      ),
    );
    expect(find.text('Missed'), findsNothing);
  });

  testWidgets('without now, nothing is marked missed', (t) async {
    await pumpAt(t, BondCaptureReview(items: _items(), onAccept: (_) {}, onDiscard: () {}));
    expect(find.text('Missed'), findsNothing);
  });

  testWidgets('accept with no edits returns the items as given', (t) async {
    List<CaptureItem>? got;
    await pumpAt(t, BondCaptureReview(items: _items(), onAccept: (v) => got = v, onDiscard: () {}));
    await _tap(t, find.text('Accept'));
    expect(got, hasLength(3));
    expect((got![0] as TaskCandidate).dueDate, '2026-03-13');
    expect(got![0].links.single.candidates.first.id, 'c1');
  });

  testWidgets('editing the title and switching task to event converts the item', (t) async {
    List<CaptureItem>? got;
    await pumpAt(t, BondCaptureReview(items: _items(), onAccept: (v) => got = v, onDiscard: () {}));
    await t.enterText(find.byType(TextField).first, 'Call Dana now');
    await t.pump();
    await _tap(t, find.text('Event').first);
    await _tap(t, find.text('Accept'));
    final first = got![0];
    expect(first, isA<EventCandidate>());
    final e = first as EventCandidate;
    expect(e.title, 'Call Dana now');
    expect(e.startDate, '2026-03-13');
    expect(e.startTime, '09:00');
    expect(e.allDay, isFalse);
  });

  testWidgets('event to task keeps date and time, and a dateless task becomes an all-day event', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [
          EventCandidate(title: 'Lunch', startDate: '2026-03-20', startTime: '12:00'),
          TaskCandidate(title: 'Pay bill', dueDate: '2026-03-21'),
        ],
        onAccept: (v) => got = v,
        onDiscard: () {},
      ),
    );
    await _tap(t, find.text('Task').first);
    await _tap(t, find.text('Event').last);
    await _tap(t, find.text('Accept'));
    final task = got![0] as TaskCandidate;
    expect((task.dueDate, task.dueTime), ('2026-03-20', '12:00'));
    final event = got![1] as EventCandidate;
    expect((event.startDate, event.allDay, event.startTime), ('2026-03-21', true, null));
    expect(find.text('All day'), findsOneWidget, reason: 'the switch is on');
  });

  for (final phone in [false, true]) {
    testWidgets('editing date, time, priority and all-day; Accept returns the edits (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      List<CaptureItem>? got;
      await pumpAt(
        t,
        BondCaptureReview(
          items: const [
            TaskCandidate(title: 'Call', dueDate: '2026-03-13', dueTime: '09:00', dueDefaulted: true),
            EventCandidate(title: 'Visit', startDate: '2026-03-20', startTime: '10:00'),
          ],
          now: _now,
          onAccept: (v) => got = v,
          onDiscard: () {},
          semanticsPrefix: 'r',
        ),
        phone: phone,
      );
      expect(find.text('Date guessed'), findsOneWidget);
      // Task: change the date (clears the guessed mark), edit the hour, set a priority.
      await _tap(t, find.bySemanticsIdentifier('r.review-item-0-due-date'));
      await _tap(t, find.bySemanticsIdentifier('r.review-item-0-due-date-day-2026-03-17'));
      expect(find.text('Date guessed'), findsNothing);
      await t.enterText(find.byType(TextField).at(1), '11');
      await t.pump();
      await _tap(t, find.text('High').first);
      // Event: all-day clears the time and keeps the date; then change that date.
      await _tap(t, find.bySemanticsIdentifier('r.review-item-1-all-day'));
      expect(find.text('Remove time'), findsOneWidget, reason: 'only the task still has a time; all-day hides the event time');
      await _tap(t, find.bySemanticsIdentifier('r.review-item-1-date'));
      await _tap(t, find.bySemanticsIdentifier('r.review-item-1-date-day-2026-03-22'));
      await _tap(t, find.text('Accept'));
      final task = got![0] as TaskCandidate;
      expect((task.dueDate, task.dueTime, task.dueDefaulted, task.priority), ('2026-03-17', '11:00', false, TaskPriority.high));
      final ev = got![1] as EventCandidate;
      expect((ev.startDate, ev.startTime, ev.allDay), ('2026-03-22', null, true));
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('a parent rebuild with an equal new list keeps the edits; different content resets', (t) async {
    final first = _items();
    await pumpAt(t, BondCaptureReview(items: first, onAccept: (_) {}, onDiscard: () {}));
    await t.enterText(find.byType(TextField).first, 'My edit');
    await t.pump();
    await pumpAt(t, BondCaptureReview(items: first.toList(), onAccept: (_) {}, onDiscard: () {}));
    expect(find.text('My edit'), findsOneWidget, reason: 'same content, new list object');
    await pumpAt(t, BondCaptureReview(items: _items().skip(1).toList(), onAccept: (_) {}, onDiscard: () {}));
    expect(find.text('My edit'), findsNothing);
    expect(find.byType(BondCaptureItemCard), findsNWidgets(2));
  });

  testWidgets('an empty title blocks Accept with an inline message on that card', (t) async {
    final got = <List<CaptureItem>>[];
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [TaskCandidate(title: 'A'), TaskCandidate(title: 'B')],
        onAccept: got.add,
        onDiscard: () {},
      ),
    );
    await t.enterText(find.byType(TextField).at(1), '   ');
    await t.pump();
    expect(find.text('Enter a title.'), findsNothing, reason: 'not before the first Accept');
    await _tap(t, find.text('Accept'));
    expect(got, isEmpty);
    expect(find.text('Enter a title.'), findsOneWidget);
    await expectNoOverlays(t);
    await t.enterText(find.byType(TextField).at(1), 'B fixed');
    await t.pump();
    expect(find.text('Enter a title.'), findsNothing);
    await _tap(t, find.text('Accept'));
    expect(got.single.map((i) => i.title), ['A', 'B fixed']);
  });

  testWidgets('after clearing the date there is no "Add a time" and Accept returns a date-less, time-less item', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [TaskCandidate(title: 'A', dueDate: '2026-03-13', dueTime: '09:00')],
        onAccept: (v) => got = v,
        onDiscard: () {},
      ),
    );
    await _tap(t, find.text('Fri, Mar 13, 2026'));
    await _tap(t, find.text('Clear'));
    expect(find.text('Add a time'), findsNothing);
    expect(find.text('Remove time'), findsNothing);
    await _tap(t, find.text('Accept'));
    final task = got!.single as TaskCandidate;
    expect((task.dueDate, task.dueTime), (null, null));
  });

  testWidgets('an item that arrives with a time and no date is refused with a message', (t) async {
    final got = <List<CaptureItem>>[];
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [TaskCandidate(title: 'A', dueTime: '09:00')],
        onAccept: got.add,
        onDiscard: () {},
      ),
    );
    await _tap(t, find.text('Accept'));
    expect(got, isEmpty);
    expect(find.text('Pick a date to set a time.'), findsOneWidget);
    await _tap(t, find.text('Remove time'));
    await _tap(t, find.text('Accept'));
    expect(got, hasLength(1));
  });

  testWidgets('a UTC now is read in the local zone: today is not "missed" and the picker opens on the local day', (t) async {
    // 2026-03-12 04:00Z is the evening of the 11th in Los Angeles (the Makefile sets TZ).
    final now = DateTime.utc(2026, 3, 12, 4);
    final local = now.toLocal();
    final key = '${local.year}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')}';
    await pumpAt(
      t,
      BondCaptureReview(
        items: [EventCandidate(title: 'All day today', startDate: key, allDay: true)],
        now: now,
        onAccept: (_) {},
        onDiscard: () {},
      ),
    );
    expect(find.text('Missed'), findsNothing, reason: "today's all-day event is not past");
    final field = t.widget<BondDateField>(find.byType(BondDateField));
    expect(field.today, DateTime(local.year, local.month, local.day));
  });

  for (final phone in [false, true]) {
    testWidgets('dropped items: none shows nothing, some shows one line (phone=$phone)', (t) async {
      final sem = t.ensureSemantics();
      await pumpAt(t, BondCaptureReview(items: _items(), onAccept: (_) {}, onDiscard: () {}, semanticsPrefix: 'c'), phone: phone);
      expect(find.textContaining('could not be read.'), findsNothing);
      await pumpAt(
        t,
        BondCaptureReview(items: _items(), dropped: 2, onAccept: (_) {}, onDiscard: () {}, semanticsPrefix: 'c'),
        phone: phone,
      );
      expect(find.text('2 items could not be read.'), findsOneWidget);
      expect(find.bySemanticsIdentifier('c.review-dropped'), findsOneWidget);
      await pumpAt(t, BondCaptureReview(items: _items(), dropped: 1, degraded: true, onAccept: (_) {}, onDiscard: () {}), phone: phone);
      expect(find.text('1 item could not be read.'), findsOneWidget);
      expect(find.text('Some items could not be read fully. Please check them.'), findsOneWidget, reason: 'beside the degraded notice');
      await expectNoOverlays(t);
      expect(t.takeException(), isNull);
      sem.dispose();
    });
  }

  testWidgets('a task time can be removed (date-only) and added back; clearing the date clears the time', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [TaskCandidate(title: 'A', dueDate: '2026-03-13', dueTime: '09:00')],
        onAccept: (v) => got = v,
        onDiscard: () {},
      ),
    );
    await _tap(t, find.text('Remove time'));
    await _tap(t, find.text('Accept'));
    expect((got!.single as TaskCandidate).dueTime, isNull);
    expect((got!.single as TaskCandidate).dueDate, '2026-03-13');
    await _tap(t, find.text('Add a time'));
    await _tap(t, find.text('Accept'));
    expect((got!.single as TaskCandidate).dueTime, '09:00');
    await _tap(t, find.text('Fri, Mar 13, 2026'));
    await _tap(t, find.text('Clear'));
    await _tap(t, find.text('Accept'));
    final task = got!.single as TaskCandidate;
    expect((task.dueDate, task.dueTime), (null, null));
  });

  testWidgets('turning all-day off gives the event a time; a missed event stops being missed when moved', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [EventCandidate(title: 'V', startDate: '2026-03-10', allDay: true)],
        now: _now,
        onAccept: (v) => got = v,
        onDiscard: () {},
        semanticsPrefix: 'r',
      ),
    );
    expect(find.text('Missed'), findsOneWidget);
    await _tap(t, find.bySemanticsIdentifier('r.review-item-0-all-day'));
    await _tap(t, find.text('Accept'));
    final ev = got!.single as EventCandidate;
    expect((ev.allDay, ev.startTime), (false, '09:00'));
    await _tap(t, find.bySemanticsIdentifier('r.review-item-0-due-date'));
    await _tap(t, find.bySemanticsIdentifier('r.review-item-0-due-date-day-2026-03-18'));
    expect(find.text('Missed'), findsNothing);
  });

  testWidgets('choosing an alternative moves it first; no match drops the link', (t) async {
    List<CaptureItem>? got;
    await pumpAt(t, BondCaptureReview(items: _items(), onAccept: (v) => got = v, onDiscard: () {}, semanticsPrefix: 'c'));
    expect(find.text('Dan Fowler'), findsOneWidget, reason: 'alternatives are shown inline');
    await _tap(t, find.text('Dan Fowler'));
    await _tap(t, find.text('Accept'));
    expect(got![0].links.single.candidates.map((o) => o.id), ['c2', 'c1']);
    await _tap(t, find.text('No match'));
    await _tap(t, find.text('Accept'));
    expect(got![0].links, isEmpty);
  });

  testWidgets('with linkSearch, a no-match link can be searched and the found record is chosen', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [
          TaskCandidate(title: 'Call Sam', links: [LinkCandidate(text: 'Sam')]),
        ],
        linkSearch: _Search(),
        onAccept: (v) => got = v,
        onDiscard: () {},
      ),
    );
    final box = find.widgetWithText(TextField, 'Search for a match');
    await t.ensureVisible(box);
    await t.enterText(box, 'Sam');
    await t.pump(const Duration(milliseconds: 300));
    await t.pump();
    await _tap(t, find.text('Found Sam').last);
    await _tap(t, find.text('Accept'));
    expect(got!.single.links.single.candidates.single.id, 'c9');
  });

  testWidgets('remove drops an item; with none left Accept is off and a line shows', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(
        items: const [TaskCandidate(title: 'A'), TaskCandidate(title: 'B')],
        onAccept: (v) => got = v,
        onDiscard: () {},
      ),
    );
    await _tap(t, find.byIcon(Icons.delete_outline).first);
    await _tap(t, find.text('Accept'));
    expect(got!.map((i) => i.title), ['B']);
    await _tap(t, find.byIcon(Icons.delete_outline));
    expect(find.text('Nothing found in that text.'), findsOneWidget);
    got = null;
    await t.tap(find.text('Accept'), warnIfMissed: false);
    expect(got, isNull);
  });

  testWidgets('priority choice lands in the accepted task', (t) async {
    List<CaptureItem>? got;
    await pumpAt(
      t,
      BondCaptureReview(items: const [TaskCandidate(title: 'A')], onAccept: (v) => got = v, onDiscard: () {}),
    );
    await _tap(t, find.text('Low'));
    await _tap(t, find.text('Accept'));
    expect((got!.single as TaskCandidate).priority, TaskPriority.low);
  });

  testWidgets('degraded shows the notice line; discard and the dictation slot work', (t) async {
    var discarded = 0;
    await pumpAt(
      t,
      BondCaptureReview(
        items: _items(),
        degraded: true,
        dictation: const BondDictationSlot(builder: _mic),
        onAccept: (_) {},
        onDiscard: () => discarded++,
      ),
    );
    expect(find.text('Some items could not be read fully. Please check them.'), findsOneWidget);
    expect(find.text('MIC'), findsOneWidget);
    await _tap(t, find.text('Discard'));
    expect(discarded, 1);
    await pumpAt(t, BondCaptureReview(items: _items(), onAccept: (_) {}, onDiscard: () {}));
    expect(find.textContaining('could not be read fully'), findsNothing);
  });
}

Widget _mic(BuildContext context) => const Text('MIC');
