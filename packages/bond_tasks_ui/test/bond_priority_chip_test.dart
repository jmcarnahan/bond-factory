import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  testWidgets('shows the label of each priority, clean at both widths', (t) async {
    for (final (p, text) in [
      (TaskPriority.low, 'Low'),
      (TaskPriority.normal, 'Normal'),
      (TaskPriority.high, 'High'),
    ]) {
      await expectCleanAtBothWidths(t, () => BondPriorityChip(priority: p));
      expect(find.text(text), findsOneWidget);
    }
  });

  testWidgets('takes its words from the labels and exposes its id', (t) async {
    final sem = t.ensureSemantics();
    await pumpAt(
      t,
      const BondPriorityChip(priority: TaskPriority.high, labels: TaskLabels(priorityHigh: 'Urgent'), semanticsId: 'pc'),
    );
    expect(find.text('Urgent'), findsOneWidget);
    expect(find.bySemanticsIdentifier('pc'), findsOneWidget);
    sem.dispose();
  });
}
