import 'dart:io';

import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the barrel exports the task widgets (a dropped export fails to compile)', () {
    final types = <Type>[
      BondCaptureItemCard, BondCaptureReview, BondCheckRow, BondChecklist,
      BondDictationSlot, BondDueLane, BondDueMarker, BondLinkChip, BondLinkPickerRow, BondPriorityChip,
      BondStageBanner, BondTaskChecklistEditor, BondTaskDeleteControl, BondTaskForm,
      BondTaskList, BondTaskQuickAdd, BondTaskRow, BondTaskSettingsForm,
      BondTaskSummaryCard, BondTodayList,
    ];
    expect(types.toSet(), hasLength(20));
  });

  test('the internal splits of the form and the capture card are not exported', () {
    final barrel = File('lib/bond_tasks_ui.dart').readAsStringSync();
    for (final internal in ['bond_task_form_due', 'bond_task_form_extras', 'bond_capture_link_row', 'bond_capture_when']) {
      expect(barrel.contains(internal), isFalse, reason: internal);
    }
  });
}
