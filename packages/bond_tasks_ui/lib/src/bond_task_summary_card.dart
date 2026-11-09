import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The four counts of `GET /tasks/summary` in a card. Overdue shows in the
/// danger tone when it is above zero.
class BondTaskSummaryCard extends StatelessWidget {
  const BondTaskSummaryCard({
    super.key,
    required this.summary,
    this.labels = const TaskLabels(),
    this.onTap,
    this.semanticsId,
  });

  final TaskSummary summary;
  final TaskLabels labels;
  final VoidCallback? onTap;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    Widget cell(String label, int n, {bool alert = false}) => Padding(
          padding: const EdgeInsets.only(right: BondSpace.s24, bottom: BondSpace.s8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('$n', style: text.title.copyWith(color: alert && n > 0 ? t.danger.press : t.ink)),
              Text(label, style: text.label),
            ],
          ),
        );
    return BondCard(
      onTap: onTap,
      semanticsId: semanticsId,
      child: Wrap(
        children: [
          cell(labels.summaryOpen, summary.open),
          cell(labels.summaryOverdue, summary.overdue, alert: true),
          cell(labels.summaryToday, summary.dueToday),
          cell(labels.summaryNoDate, summary.noDate),
        ],
      ),
    );
  }
}
