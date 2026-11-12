import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/src/capture_item_build.dart';
import 'package:flutter_test/flutter_test.dart';

const _event = EventCandidate(
  title: 'Site meeting',
  startDate: '2026-03-13',
  startTime: '10:00',
  location: 'Main yard',
  notes: 'Bring the plans',
  durationMinutes: 90,
  attendees: ['Dana', 'Lee'],
);

CaptureItem _edit(CaptureItem item, {EventCandidate? remembered, bool isEvent = true, String? time = '10:00', String? endTime}) =>
    buildEditedCaptureItem(
      item,
      remembered: remembered,
      title: item.title,
      links: const [],
      isEvent: isEvent,
      date: '2026-03-13',
      time: time,
      allDay: time == null,
      defaulted: false,
      endDate: endTime == null ? null : '2026-03-13',
      endTime: endTime,
      priority: null,
    );

void main() {
  test('the stated length is kept while the times are untouched', () {
    expect((_edit(_event) as EventCandidate).durationMinutes, 90);
  });

  test('the stated length is dropped once the start or the end is edited, or the event becomes all day', () {
    expect((_edit(_event, time: '11:00') as EventCandidate).durationMinutes, isNull);
    expect((_edit(_event, endTime: '12:00') as EventCandidate).durationMinutes, isNull);
    expect((_edit(_event, time: null) as EventCandidate).durationMinutes, isNull);
  });

  test('event to task and back keeps the place and the guests; the notes are the task\'s', () {
    final task = _edit(_event, isEvent: false) as TaskCandidate;
    expect(task.notes, 'Bring the plans');
    final back = _edit(task, remembered: _event) as EventCandidate;
    expect(back.location, 'Main yard');
    expect(back.attendees, ['Dana', 'Lee']);
    expect(back.notes, 'Bring the plans');
    expect(back.durationMinutes, 90);
  });

  test('a task that never was an event becomes a plain event', () {
    const task = TaskCandidate(title: 'Call Dana', notes: 'Ask about the quote');
    final event = _edit(task) as EventCandidate;
    expect(event.location, isNull);
    expect(event.attendees, isEmpty);
    expect(event.notes, 'Ask about the quote');
  });
}
