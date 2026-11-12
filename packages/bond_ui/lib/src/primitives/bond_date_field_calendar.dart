import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_chip.dart';
import 'bond_date_format.dart';

/// 15-minute chips, scrollable inside a fixed-height box. Internal to
/// bond_ui.
class BondTimeChips extends StatelessWidget {
  const BondTimeChips({
    super.key,
    required this.selected,
    required this.startHour,
    required this.endHour,
    required this.onSelect,
    this.semanticsId,
  });

  final DateTime? selected;
  final int startHour;
  final int endHour;
  final void Function(int hour, int minute) onSelect;
  final String? semanticsId;

  static const double _maxHeight = 200;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final labels = BondLabels.of(context);
    return Container(
      constraints: const BoxConstraints(maxHeight: _maxHeight),
      padding: BondSpace.all8,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: t.line),
      ),
      child: SingleChildScrollView(
        child: Wrap(
          spacing: BondSpace.s8,
          runSpacing: BondSpace.s8,
          children: [
            for (var h = startHour; h <= endHour; h++)
              for (var m = 0; m < 60; m += 15)
                BondChip(
                  label: BondDateFormat.time(labels, DateTime(2000, 1, 1, h, m)),
                  selected:
                      selected != null && selected!.hour == h && selected!.minute == m,
                  onTap: () => onSelect(h, m),
                  semanticsId: semanticsId == null
                      ? null
                      : bondSemanticsOption(semanticsId!,
                          '${h.toString().padLeft(2, '0')}${m.toString().padLeft(2, '0')}'),
                ),
          ],
        ),
      ),
    );
  }
}
