import 'package:bond_tasks/bond_tasks.dart';
import 'package:test/test.dart';

void main() {
  test('overridden parses from the list and toJson writes it in field order', () {
    final s = TaskSettings.fromJson({'end_of_day': '18:00', 'overridden': ['lead_minutes', 'end_of_day']});
    expect(s.overridden, {'lead_minutes', 'end_of_day'});
    expect(s.isOverridden('end_of_day'), isTrue);
    expect(s.isOverridden('start_of_day'), isFalse);
    expect(s.toJson()['overridden'], ['end_of_day', 'lead_minutes']);
    expect(TaskSettings.fromJson({'overridden': []}).overridden, isEmpty);
    expect(const TaskSettings(overridden: {}).toJson()['overridden'], isEmpty, reason: 'emitted when known, as the shared fixture has it');
  });

  test('reset sends an explicit null and wins over a value; absent stays absent', () {
    expect(const TaskSettingsPatch(reset: {'end_of_day'}).toJson(), {'end_of_day': null});
    expect(const TaskSettingsPatch(endOfDay: '18:00', reset: {'end_of_day', 'time_zone'}).toJson(),
        {'time_zone': null, 'end_of_day': null});
    expect(const TaskSettingsPatch(leadMinutes: 5).toJson(), {'lead_minutes': 5});
    expect(const TaskSettingsPatch().toJson(), isEmpty);
  });
}
