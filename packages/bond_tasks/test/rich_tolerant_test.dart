import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_json/bond_json.dart' show JsonShapeError;
import 'package:test/test.dart';

EventCandidate _event(Map<String, Object?> extra) => ParseResult.fromJson({
      'items': [
        {'kind': 'event', 'title': 'Visit', 'start_date': '2026-11-12', ...extra},
      ],
    }).items.single as EventCandidate;

TaskCandidate _task(Map<String, Object?> extra) => ParseResult.fromJson({
      'items': [
        {'kind': 'task', 'title': 'Call', ...extra},
      ],
    }).items.single as TaskCandidate;

void main() {
  test('attendees keep only non-blank strings', () {
    final e = _event({'attendees': ['Dana', null, 5, '', '  ', true, 'Lee', {}]});
    expect(e.attendees, ['Dana', 'Lee']);
  });

  test('wrong-typed rich keys read as null or empty and do not fail the parse', () {
    final e = _event({
      'location': 5,
      'notes': <String, Object?>{},
      'attendees': 'Dana',
      'duration_minutes': true,
    });
    expect(e.title, 'Visit');
    expect(e.location, isNull);
    expect(e.notes, isNull);
    expect(e.attendees, isEmpty);
    expect(e.durationMinutes, isNull);
    expect(_task({'notes': 7}).notes, isNull);
    expect(_task({'notes': 7}).title, 'Call');
  });

  test('duration: whole positive numbers only', () {
    expect(_event({'duration_minutes': 45}).durationMinutes, 45);
    expect(_event({'duration_minutes': 45.0}).durationMinutes, 45);
    expect(_event({'duration_minutes': '30'}).durationMinutes, 30);
    for (final bad in [0, -5, 1.5, 'abc', null, [], double.nan]) {
      expect(_event({'duration_minutes': bad}).durationMinutes, isNull, reason: '$bad');
    }
  });

  test('right-typed rich keys still read', () {
    final e = _event({'location': 'Site', 'notes': 'Bring plans', 'attendees': ['Dana']});
    expect([e.location, e.notes, e.attendees], ['Site', 'Bring plans', ['Dana']]);
  });

  test('the required v1 keys stay strict', () {
    expect(
      () => ParseResult.fromJson({
        'items': [
          {'kind': 'event', 'title': 5},
        ],
      }),
      throwsA(isA<JsonShapeError>()),
    );
    expect(
      () => _task({'due_date': 5}),
      throwsA(isA<JsonShapeError>()),
    );
  });
}
