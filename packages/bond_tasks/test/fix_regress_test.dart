import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

void main() {
  test('ticker_first_tick_after_midnight_shift_emits_day', () async {
    var now = DateTime(2026, 3, 12, 23, 59, 30).toUtc();
    final ticker = TaskTicker(clock: TaskClock(() => now));
    final minutes = <DateTime>[], days = <DateTime>[];
    final a = ticker.minutes.listen(minutes.add);
    final b = ticker.days.listen(days.add);
    now = DateTime(2026, 3, 13, 0, 0, 5).toUtc();
    ticker.tick();
    await Future<void>.delayed(Duration.zero);
    expect(minutes, hasLength(1));
    expect(days, hasLength(1));
    await a.cancel();
    await b.cancel();
    ticker.dispose();
  });

  test('settings_overridden_unknown_when_key_absent', () {
    final s = TaskSettings.fromJson({'end_of_day': '18:00'});
    expect(s.overridden, isNull);
    expect(s.overriddenKnown, isFalse);
    expect(s.isOverridden('end_of_day'), isFalse);
    expect(s.toJson().containsKey('overridden'), isFalse);
    final k = TaskSettings.fromJson({'overridden': []});
    expect(k.overriddenKnown, isTrue);
    expect(k.toJson()['overridden'], isEmpty);
  });

  test('task_extras_from_json_is_unmodifiable', () {
    final t = Task.fromJson({'id': 'a', 'title': 'T', 'loan_id': 'L1'});
    expect(t.extras, {'loan_id': 'L1'});
    expect(() => t.extras['x'] = 1, throwsUnsupportedError);
  });

  test('draft_and_patch_extras_cannot_inject_known_keys', () {
    final d = const TaskDraft(title: 'T', extras: {'due_date': 'x', 'time_zone': 'Z', 'status': 'done', 'ok': 1}).toJson();
    expect(d.containsKey('due_date'), isFalse);
    expect(d.containsKey('time_zone'), isFalse);
    expect(d.containsKey('status'), isFalse);
    expect(d['ok'], 1);
    final p = const TaskPatch(extras: {'due_date': 'x', 'priority': 'high', 'ok': 1}).toJson();
    expect(p, {'ok': 1});
  });
}
