import 'package:bond_tasks/bond_tasks.dart';

/// The item as the card now stands. Every field the card does not edit (location, notes, duration,
/// attendees, flags, confidence) is kept from [item]; on a change of kind the notes carry over, and a
/// switch back to an event takes the place and guests from [remembered]. The length in minutes is
/// dropped once the start or end is edited.
CaptureItem buildEditedCaptureItem(
  CaptureItem item, {
  EventCandidate? remembered,
  required String title,
  required List<LinkCandidate> links,
  required bool isEvent,
  required String? date,
  required String? time,
  required bool allDay,
  required bool defaulted,
  required String? endDate,
  required String? endTime,
  required TaskPriority? priority,
}) {
  final notes = switch (item) {
    TaskCandidate() => item.notes,
    EventCandidate() => item.notes,
  };
  final startTime = allDay ? null : time;
  if (isEvent) {
    // Back from a task: the event the card last held gives its place and guests again; the notes are the task's.
    final base = item is EventCandidate
        ? item
        : (remembered?.copyWith(notes: notes, clearNotes: notes == null) ?? EventCandidate(title: title, notes: notes));
    // The stated length holds only while the times it was stated for are untouched.
    final sameTimes = !allDay && startTime == base.startTime && endDate == base.endDate && endTime == base.endTime;
    return EventCandidate(
      title: title,
      links: links,
      confidence: item.confidence,
      flags: item.flags,
      degraded: item.degraded,
      startDate: date,
      startTime: startTime,
      allDay: allDay,
      endDate: endDate,
      endTime: endTime,
      location: base.location,
      notes: base.notes,
      durationMinutes: sameTimes ? base.durationMinutes : null,
      attendees: base.attendees,
    );
  }
  return TaskCandidate(
    title: title,
    links: links,
    confidence: item.confidence,
    flags: item.flags,
    degraded: item.degraded,
    dueDate: date,
    dueTime: time,
    dueDefaulted: defaulted,
    priority: priority,
    notes: notes,
  );
}
