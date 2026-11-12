import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// A small count for a month cell ("3"); danger-coloured when [overdue].
/// Draws nothing for a count of zero. Meant for a `BondMonthGrid.dayBuilder`;
/// a grid cell hides its children from screen readers, so also pass
/// `daySemantics: (day) => labels.markerText(count, overdue: ...)` to the grid
/// (empty text for a day with no marker).
class BondDueMarker extends StatelessWidget {
  const BondDueMarker({
    super.key,
    required this.count,
    this.overdue = false,
    this.labels = const TaskLabels(),
    this.semanticsId,
  });

  final int count;
  final bool overdue;
  final TaskLabels labels;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    if (count <= 0) return const SizedBox.shrink();
    final t = BondTokens.of(context);
    final c = t.colorsFor(overdue ? BondToneRole.danger : BondToneRole.accent);
    return Semantics(
      identifier: semanticsId,
      label: labels.markerText(count, overdue: overdue),
      container: true,
      child: ExcludeSemantics(
        child: Container(
          margin: const EdgeInsets.only(top: BondSpace.s4),
          padding: const EdgeInsets.symmetric(horizontal: BondSpace.s4),
          decoration: BoxDecoration(
            color: c.background,
            borderRadius: BondRadius.pillAll,
            border: Border.all(color: c.border),
          ),
          child: Text('$count', style: BondText(t).style(BondText.label13, BondText.semibold, color: c.foreground)),
        ),
      ),
    );
  }
}
