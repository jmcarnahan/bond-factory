import 'dart:convert';
import 'dart:io';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

// Run with TZ=America/Los_Angeles: the shared cases are expressed in that zone.
final bool _la = DateTime.now().timeZoneName == 'PST' || DateTime.now().timeZoneName == 'PDT';
final Object _skip = _la ? false : 'run with TZ=America/Los_Angeles (device zone is ${DateTime.now().timeZoneName})';

List<Map<String, Object?>> _cases() {
  final all = jsonDecode(File('../../fixtures/tasks/stage_times.json').readAsStringSync()) as List;
  return [
    for (final c in all.cast<Map<String, Object?>>())
      if (c['effective_zone'] == 'America/Los_Angeles') c,
  ];
}

DateTime _t(Object? s) => DateTime.parse(s! as String);

TaskPrefs _prefs(Map<String, Object?> c) {
  final p = c['prefs']! as Map;
  return TaskPrefs(
    startOfDay: p['start_of_day']! as String,
    endOfDay: p['end_of_day']! as String,
    leadMinutes: p['lead_minutes']! as int,
    maxPast: c['max_past']! as int,
  );
}

Task _task(Map<String, Object?> c) => Task.fromJson(c['task']! as Map<String, Object?>);

Task _timed({int remind = -3, String? assignee, DateTime? dueAt}) => Task(
      id: 'task-x',
      title: 'x',
      dueDate: '2026-03-12',
      dueTime: '09:30',
      dueAt: dueAt ?? DateTime.utc(2026, 3, 12, 16, 30),
      ownerUserId: 'user-1',
      assignedUserId: assignee,
      remindMinutesBefore: remind,
    );

Task _dateOnly({DateTime? dueAt, String? assignee}) => Task(
      id: 'task-y',
      title: 'y',
      dueDate: '2026-03-12',
      dueAt: dueAt,
      ownerUserId: 'user-1',
      assignedUserId: assignee,
      remindMinutesBefore: kRemindUseDefault,
    );

void main() {
  final cases = _cases();

  test('the fixture has Los Angeles cases', () => expect(cases.length, greaterThan(40)));

  group('fixture cases (America/Los_Angeles)', () {
    for (final c in cases) {
      final name = c['name']! as String;
      final t = _task(c);
      final p = _prefs(c);
      final now = _t(c['now']);
      final user = c['user_id']! as String;

      test('$name: stages', skip: _skip, () {
        final got = stageTimesFor(t, p, now, userId: user);
        final want = (c['stages']! as List).cast<Map<String, Object?>>();
        expect([for (final s in got) '${s.stage}/${s.seq}'], [for (final s in want) '${s['stage']}/${s['seq']}']);
        for (var i = 0; i < want.length; i++) {
          final w = want[i];
          expect(got[i].at, _t(w['at']), reason: '$name at ${w['stage']}/${w['seq']}');
          expect(got[i].last, w['last'], reason: '$name last');
          expect(got[i].sendAt, w['send_at'] == null ? isNull : _t(w['send_at']), reason: '$name sendAt');
        }
      });

      test('$name: current, sendable, token, notice id', skip: _skip, () {
        final cur = currentStage(t, p, now, userId: user);
        final want = c['current'] as Map<String, Object?>?;
        if (want == null) {
          expect(cur, isNull);
        } else {
          expect(cur!.stage, want['stage']);
          expect(cur.seq, want['seq']);
          expect(cur.at, _t(want['at']));
          expect(cur.last, want['last']);
        }
        expect(isSendableNow(t, p, now, userId: user), c['sendable']);
        expect(deadlineToken(t), c['token']);
        if (cur != null) {
          expect(noticeId(t.id, user, cur.stage, cur.seq, deadlineToken(t)), c['notice_id']);
        } else {
          expect(c['notice_id'], isNull);
        }
      });
    }
  });

  group('stageTimes without a user', () {
    test('lists close, due and every past stage for the responsible schedule', skip: _skip, () {
      final s = stageTimes(_timed(), const TaskPrefs(), DateTime.utc(2026, 3, 12, 15));
      expect([for (final x in s) '${x.stage}/${x.seq}'], ['close/0', 'due/0', 'past/0', 'past/1', 'past/2', 'past/3', 'past/4', 'past/5']);
      expect(s.last.last, isTrue);
      expect(s.where((x) => x.last).length, 1);
    });

    test('pastDays drops old stages', skip: _skip, () {
      final now = DateTime.utc(2026, 3, 16, 12);
      final s = stageTimes(_timed(), const TaskPrefs(), now, pastDays: 2);
      expect(s.first.stage, 'past');
      expect(s.first.seq, 2); // seq 2 starts 3-14 15:00Z, inside the 2 days; seq 1 (3-13) is dropped
    });

    test('a closed task has no stages', () {
      final t = _timed().copyWith(status: TaskStatus.done);
      expect(stageTimes(t, const TaskPrefs(), DateTime.utc(2026, 3, 12)), isEmpty);
      expect(stageOf(t, const TaskPrefs(), DateTime.utc(2026, 3, 12)), TaskStage.none);
    });
  });

  group('null dueAt', () {
    test('timed with unknown dueAt: no stages, empty token', skip: _skip, () {
      const t = Task(id: 'a', title: 'a', dueDate: '2026-03-12', dueTime: '09:30', ownerUserId: 'user-1');
      expect(stageTimes(t, const TaskPrefs(), DateTime.utc(2026, 3, 12, 20)), isEmpty);
      expect(stageTimesFor(t, const TaskPrefs(), DateTime.utc(2026, 3, 12, 20), userId: 'user-1'), isEmpty);
      expect(stageOf(t, const TaskPrefs(), DateTime.utc(2026, 3, 12, 20)), TaskStage.none);
      expect(deadlineToken(t), '');
    });

    test('date-only for the device user is scheduled from the local end of day', skip: _skip, () {
      final now = DateTime.utc(2026, 3, 12, 20);
      final withAt = stageTimesFor(_dateOnly(dueAt: DateTime.utc(2026, 3, 13)), const TaskPrefs(), now, userId: 'user-1');
      final without = stageTimesFor(_dateOnly(), const TaskPrefs(), now, userId: 'user-1');
      expect([for (final s in without) (s.stage, s.seq, s.at, s.sendAt)], [for (final s in withAt) (s.stage, s.seq, s.at, s.sendAt)]);
      expect(without.map((s) => '${s.stage}/${s.seq}').first, 'close/0');
    });

    test('date-only of another user: only the mornings, from the date', skip: _skip, () {
      final t = _dateOnly(assignee: 'user-2');
      final s = stageTimesFor(t, const TaskPrefs(), DateTime.utc(2026, 3, 12, 20), userId: 'user-1');
      expect([for (final x in s) '${x.stage}/${x.seq}'], ['past/1', 'past/2', 'past/3', 'past/4', 'past/5']);
      expect(s.first.at, DateTime(2026, 3, 13, 8).toUtc());
      expect(s.first.sendAt, s.first.at);
    });
  });

  group('stageOf', () {
    test('upcoming before the close stage, then close, due, past, none', skip: _skip, () {
      const p = TaskPrefs();
      final t = _timed();
      expect(stageOf(t, p, DateTime.utc(2026, 3, 12, 15, 29)), TaskStage.upcoming);
      expect(stageOf(t, p, DateTime.utc(2026, 3, 12, 15, 30)), TaskStage.close);
      expect(stageOf(t, p, DateTime.utc(2026, 3, 12, 16, 30)), TaskStage.due);
      expect(stageOf(t, p, DateTime.utc(2026, 3, 12, 16, 45)), TaskStage.past);
      expect(stageOf(t, p, DateTime.utc(2026, 3, 18, 15)), TaskStage.none);
    });

    test('an undated task is none', () {
      const t = Task(id: 'u', title: 'u', ownerUserId: 'user-1');
      expect(stageOf(t, const TaskPrefs(), DateTime.utc(2026, 3, 12)), TaskStage.none);
    });
  });

  group('stageTimesFor', () {
    test('the owner of an assigned task gets only past; a stranger gets nothing', skip: _skip, () {
      final t = _timed(assignee: 'user-2');
      final now = DateTime.utc(2026, 3, 12, 15);
      expect(stageTimesFor(t, const TaskPrefs(), now, userId: 'user-1').map((s) => s.stage).toSet(), {'past'});
      expect(stageTimesFor(t, const TaskPrefs(), now, userId: 'user-2').map((s) => s.stage).toSet(), {'close', 'due', 'past'});
      expect(stageTimesFor(t, const TaskPrefs(), now, userId: 'user-3'), isEmpty);
      expect(stageTimesFor(t, const TaskPrefs(), now, userId: ''), isEmpty);
    });
  });

  group('date-only task written in another zone', () {
    // 2026-11-20 17:00 in Sydney is 2026-11-19 22:00 in Los Angeles.
    final t = Task(
      id: 'syd',
      title: 'syd',
      dueDate: '2026-11-20',
      dueAt: DateTime.utc(2026, 11, 20, 6),
      ownerUserId: 'user-1',
      remindMinutesBefore: kRemindMorningOf,
    );
    final now = DateTime.utc(2026, 11, 19, 10);

    test('the mornings count from the device-local date of dueAt, not the dueDate string', skip: _skip, () {
      final s = stageTimes(t, const TaskPrefs(), now);
      final p1 = s.firstWhere((x) => x.stage == 'past' && x.seq == 1);
      expect(p1.at, DateTime(2026, 11, 20, 8).toUtc());
      expect(s.firstWhere((x) => x.seq == 5 && x.stage == 'past').at, DateTime(2026, 11, 24, 8).toUtc());
    });

    test('the morning close is the morning of that local date', skip: _skip, () {
      final s = stageTimes(t, const TaskPrefs(), now);
      expect(s.first.stage, 'close');
      expect(s.first.at, DateTime(2026, 11, 19, 8).toUtc());
    });

    test('the same notice time for the owner-only view', skip: _skip, () {
      final s = stageTimesFor(t, const TaskPrefs(), now, userId: 'user-1');
      expect(s.firstWhere((x) => x.stage == 'past' && x.seq == 1).at, DateTime(2026, 11, 20, 8).toUtc());
    });
  });

  group('past seq 0', () {
    Task dueAtLocal(int h, int m) => Task(
          id: 'edge',
          title: 'edge',
          dueDate: '2026-03-12',
          dueTime: '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}',
          dueAt: DateTime(2026, 3, 12, h, m).toUtc(),
          ownerUserId: 'user-1',
          remindMinutesBefore: kRemindNone,
        );
    // The first morning (seq 1) is startOfDay on the day AFTER the due local date, so with startOfDay
    // 00:00 the boundary is due 23:45 (+ 15 min = exactly 00:00 next day).
    List<String> kinds(Task t) => [
          for (final s in stageTimes(t, const TaskPrefs(startOfDay: '00:00'), DateTime.utc(2026, 3, 12))) '${s.stage}/${s.seq}',
        ];

    test('past 0 is listed only when it comes strictly before the first morning', skip: _skip, () {
      expect(kinds(dueAtLocal(23, 45)), ['due/0', 'past/1', 'past/2', 'past/3', 'past/4', 'past/5']);
      expect(kinds(dueAtLocal(23, 44)), ['due/0', 'past/0', 'past/1', 'past/2', 'past/3', 'past/4', 'past/5']);
    });

    test('is left out when dueAt + 15 minutes is not before the next morning', skip: _skip, () {
      // Due 23:55 local with a work day starting at 00:00: seq 0 would start at 00:10, after seq 1 (00:00).
      final due = DateTime(2026, 3, 12, 23, 55).toUtc();
      final t = Task(id: 'q', title: 'q', dueDate: '2026-03-12', dueTime: '23:55', dueAt: due, ownerUserId: 'user-1');
      final s = stageTimes(t, const TaskPrefs(startOfDay: '00:00'), DateTime.utc(2026, 3, 12));
      expect(s.where((x) => x.stage == 'past').first.seq, 1);
      expect(s.any((x) => x.stage == 'past' && x.seq == 0), isFalse);
    });
  });

  group('malformed prefs', () {
    List<(String, int, DateTime, DateTime?)> shape(TaskPrefs p) => [
          for (final s in stageTimes(_timed(), p, DateTime.utc(2026, 3, 12, 15))) (s.stage, s.seq, s.at, s.sendAt),
        ];

    test('a bad start or end time reads as the default and never throws', () {
      for (final bad in ['bad', '25:61', '', '8', '24:00', '12:5', '08:00:00']) {
        final p = TaskPrefs(startOfDay: bad, endOfDay: bad);
        expect(() => shape(p), returnsNormally, reason: bad);
        expect(shape(p), shape(const TaskPrefs()), reason: bad);
        expect(() => inQuietHours(p, DateTime(2026, 3, 12, 20)), returnsNormally);
        expect(inQuietHours(p, DateTime(2026, 3, 12, 20)), inQuietHours(const TaskPrefs(), DateTime(2026, 3, 12, 20)));
      }
    });

    test('date-only with no dueAt (uses the end of day) does not throw either', () {
      final t = _dateOnly(assignee: null);
      expect(() => stageTimes(t, const TaskPrefs(endOfDay: 'x'), DateTime.utc(2026, 3, 12)), returnsNormally);
    });

    test('a single-digit hour is accepted', () {
      expect(shape(const TaskPrefs(startOfDay: '7:30')), shape(const TaskPrefs(startOfDay: '07:30')));
      expect(shape(const TaskPrefs(startOfDay: '7:30')), isNot(shape(const TaskPrefs())));
    });
  });

  group('lead', () {
    test('a lead over a week counts as a week', skip: _skip, () {
      final s = stageTimes(_timed(remind: 600000), const TaskPrefs(), DateTime.utc(2026, 3, 1));
      expect(s.first.stage, 'close');
      expect(s.first.at, DateTime.utc(2026, 3, 12, 16, 30).subtract(const Duration(minutes: 10080)));
    });
  });
}
