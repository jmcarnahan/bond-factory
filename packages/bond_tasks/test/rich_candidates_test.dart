import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

Map<String, Object?> _load(String path) => (jsonDecode(File(path).readAsStringSync()) as Map).cast<String, Object?>();

const _dir = '../../fixtures/capture';

EventCandidate _event(ParseResult r) => r.items.whereType<EventCandidate>().single;
TaskCandidate _task(ParseResult r) => r.items.whereType<TaskCandidate>().single;

void _checkRich(Map<String, Object?> wire) {
  final r = ParseResult.fromJson(wire);
  final items = wire['items']! as List;
  for (final raw in items.cast<Map<String, Object?>>()) {
    if (raw['kind'] == 'event') {
      final e = r.items.whereType<EventCandidate>().firstWhere((c) => c.title == raw['title']);
      expect(e.location, raw['location']);
      expect(e.notes, raw['notes']);
      expect(e.durationMinutes, raw['duration_minutes']);
      expect(e.attendees, raw['attendees'] ?? const []);
      expect(e.endTime, raw['end_time']);
    } else {
      final t = r.items.whereType<TaskCandidate>().firstWhere((c) => c.title == raw['title']);
      expect(t.notes, raw['notes']);
      expect(t.toDraft().notes, raw['notes']);
    }
  }
}

void main() {
  group('rich keys, inline (PLAN R8 shape)', () {
    final wire = {
      'items': [
        {
          'kind': 'event',
          'title': 'Site meeting',
          'start_date': '2026-11-12',
          'start_time': '14:00',
          'end_time': '15:30',
          'location': 'Example Plaza office',
          'notes': 'Bring drawings',
          'duration_minutes': 90,
          'attendees': ['Dana', 'Lee'],
        },
        {'kind': 'task', 'title': 'Call Sam', 'notes': 'Ask about the invoice'},
      ],
    };
    test('event and task read the rich keys', () {
      final r = ParseResult.fromJson(wire);
      final e = _event(r);
      expect(e.location, 'Example Plaza office');
      expect(e.notes, 'Bring drawings');
      expect(e.durationMinutes, 90);
      expect(e.attendees, ['Dana', 'Lee']);
      expect(_task(r).notes, 'Ask about the invoice');
    });
    test('task notes ride into the draft', () {
      final d = _task(ParseResult.fromJson(wire)).toDraft();
      expect(d.notes, 'Ask about the invoice');
      expect(d.toJson()['notes'], 'Ask about the invoice');
    });
    test('copyWith keeps the rich fields and clear flags clear them', () {
      final e = _event(ParseResult.fromJson(wire));
      final c = e.copyWith(title: 'Renamed');
      expect([c.location, c.notes, c.durationMinutes, c.attendees], ['Example Plaza office', 'Bring drawings', 90, ['Dana', 'Lee']]);
      final cleared = e.copyWith(clearLocation: true, clearNotes: true, clearDurationMinutes: true, attendees: const []);
      expect([cleared.location, cleared.notes, cleared.durationMinutes, cleared.attendees], [null, null, null, <String>[]]);
      final t = _task(ParseResult.fromJson(wire));
      expect(t.copyWith(title: 'x').notes, 'Ask about the invoice');
      expect(t.copyWith(clearNotes: true).notes, isNull);
    });
    test('null rich keys read as null and an empty attendee list', () {
      final e = EventCandidate.fromJson({'kind': 'event', 'title': 'x', 'location': null, 'attendees': null});
      expect([e.location, e.notes, e.durationMinutes, e.attendees], [null, null, null, <String>[]]);
    });
  });

  group('absent keys leave today\'s objects', () {
    test('the default fixture has no rich fields and its draft has no notes', () {
      final r = ParseResult.fromJson(_load('$_dir/expected_candidates.json'));
      for (final i in r.items) {
        if (i is EventCandidate) {
          expect([i.location, i.notes, i.durationMinutes, i.attendees], [null, null, null, <String>[]]);
        } else if (i is TaskCandidate) {
          expect(i.notes, isNull);
          expect(i.toDraft().notes, isNull);
          expect(i.toDraft().toJson().containsKey('notes'), isFalse);
        }
      }
    });
  });

  group('fixtures/capture rich files', () {
    final files = Directory(_dir)
        .listSync()
        .whereType<File>()
        .where((f) => f.uri.pathSegments.last.contains('rich') && f.path.endsWith('.json'))
        .toList();
    test('at least the expected rich candidate files exist', () {
      final names = files.map((f) => f.uri.pathSegments.last).toSet();
      expect(names, containsAll(['expected_candidates_rich.json', 'expected_degraded_rich.json']));
    });
    for (final f in files) {
      final name = f.uri.pathSegments.last;
      if (!name.startsWith('expected_')) continue;
      test('$name parses and carries the rich fields', () => _checkRich(_load(f.path)));
    }
    test('expected_candidates_rich: known values', () {
      final r = ParseResult.fromJson(_load('$_dir/expected_candidates_rich.json'));
      final e = _event(r);
      expect([e.location, e.notes, e.durationMinutes, e.attendees], ['Example Plaza office', 'Bring the permit drawings', 90, ['Dana', 'Lee']]);
      expect([e.startTime, e.endTime], ['14:00', '15:30']);
      expect(_task(r).notes, 'Ask about the invoice');
      expect(_task(r).links.single.candidates, isEmpty);
    });
  });
}
