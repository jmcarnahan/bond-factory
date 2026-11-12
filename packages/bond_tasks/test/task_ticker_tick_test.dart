import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

void main() {
  test('task_clock_offset: runs ahead and behind, the base is untouched', () {
    final base = TaskClock(() => DateTime.utc(2026, 3, 12, 9));
    expect(base.offsetBy(const Duration(hours: 2)).nowUtc(), DateTime.utc(2026, 3, 12, 11));
    expect(base.offsetBy(const Duration(days: -1)).nowUtc(), DateTime.utc(2026, 3, 11, 9));
    expect(base.nowUtc(), DateTime.utc(2026, 3, 12, 9));
    expect(base.offsetBy(const Duration(hours: 1)).offsetBy(const Duration(hours: 1)).nowUtc(), DateTime.utc(2026, 3, 12, 11));
  });

  test('task_ticker_tick_emits_minute_and_day', () async {
    var now = DateTime(2026, 3, 12, 9, 30).toUtc();
    final ticker = TaskTicker(clock: TaskClock(() => now));
    final minutes = <DateTime>[], days = <DateTime>[];
    final a = ticker.minutes.listen(minutes.add);
    final b = ticker.days.listen(days.add);

    ticker.tick();
    await Future<void>.delayed(Duration.zero);
    expect(minutes, [now]);
    expect(days, isEmpty, reason: 'same local date');

    now = DateTime(2026, 3, 13, 0, 5).toUtc();
    ticker.tick();
    await Future<void>.delayed(Duration.zero);
    expect(minutes, hasLength(2));
    expect(days, [now]);

    ticker.tick();
    await Future<void>.delayed(Duration.zero);
    expect(minutes, hasLength(3));
    expect(days, hasLength(1), reason: 'the date has not changed since the last day tick');

    await a.cancel();
    await b.cancel();
    ticker.dispose();
  });
}
