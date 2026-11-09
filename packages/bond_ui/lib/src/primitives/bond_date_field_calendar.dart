import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_chip.dart';
import 'bond_date_format.dart';
import 'bond_pressable.dart';

/// The expanded month grid of `BondDateField`: month header with previous and
/// next, weekday initials (Sunday first) and six weeks of day cells. Internal
/// to bond_ui.
class BondMonthGrid extends StatelessWidget {
  const BondMonthGrid({
    super.key,
    required this.visibleMonth,
    required this.selected,
    required this.today,
    required this.onPrevious,
    required this.onNext,
    required this.onSelect,
    required this.isSelectable,
    this.semanticsId,
  });

  final DateTime visibleMonth;
  final DateTime? selected;
  final DateTime today;
  final VoidCallback onPrevious;
  final VoidCallback onNext;
  final ValueChanged<DateTime> onSelect;
  final bool Function(DateTime day) isSelectable;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final labels = BondLabels.of(context);
    // Sunday-first. weekday is 1..7 (Mon..Sun), so Sunday has no lead-in. Day
    // arithmetic goes through the DateTime constructor, never Duration:
    // adding 7 absolute days across a DST change duplicates a date.
    final firstOfMonth = DateTime(visibleMonth.year, visibleMonth.month);
    final leadIn = firstOfMonth.weekday % 7;
    final gridStart =
        DateTime(visibleMonth.year, visibleMonth.month, 1 - leadIn);
    // Sunday first: Sun, then Mon..Sat from the Monday-first list.
    final initials = [
      for (var i = 0; i < 7; i++)
        labels.weekdayShort[(i + 6) % 7].substring(0, 1),
    ];

    return Container(
      padding: BondSpace.all8,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: t.line),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              _NavButton(
                icon: Icons.chevron_left,
                label: labels.previousMonth,
                onPressed: onPrevious,
                semanticsId:
                    semanticsId == null ? null : '$semanticsId-prev',
              ),
              Expanded(
                child: Text(
                  BondDateFormat.month(labels, visibleMonth),
                  textAlign: TextAlign.center,
                  style: text.smallStrong,
                ),
              ),
              _NavButton(
                icon: Icons.chevron_right,
                label: labels.nextMonth,
                onPressed: onNext,
                semanticsId:
                    semanticsId == null ? null : '$semanticsId-next',
              ),
            ],
          ),
          BondSpace.h4,
          Row(
            children: [
              for (final d in initials)
                Expanded(child: Center(child: Text(d, style: text.label))),
            ],
          ),
          BondSpace.h4,
          for (var week = 0; week < 6; week++)
            Row(
              children: [
                for (var day = 0; day < 7; day++)
                  Expanded(
                    child: _DayCell(
                      date: DateTime(gridStart.year, gridStart.month,
                          gridStart.day + week * 7 + day),
                      visibleMonth: visibleMonth,
                      selected: selected,
                      today: today,
                      onSelect: onSelect,
                      isSelectable: isSelectable,
                      semanticsId: semanticsId,
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    required this.date,
    required this.visibleMonth,
    required this.selected,
    required this.today,
    required this.onSelect,
    required this.isSelectable,
    required this.semanticsId,
  });

  final DateTime date;
  final DateTime visibleMonth;
  final DateTime? selected;
  final DateTime today;
  final ValueChanged<DateTime> onSelect;
  final bool Function(DateTime day) isSelectable;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final inMonth =
        date.month == visibleMonth.month && date.year == visibleMonth.year;
    final isSelected = selected != null && BondDateFormat.sameDay(date, selected!);
    final isToday = BondDateFormat.sameDay(date, today);
    final enabled = isSelectable(date);
    final Color ink = isSelected
        ? t.onFill
        : (!enabled || !inMonth ? t.lineStrong : t.ink);

    return bondSemantics(
      id: semanticsId == null
          ? null
          : bondSemanticsOption(semanticsId!, BondDateFormat.iso(date)),
      label: '${date.day}',
      button: true,
      enabled: enabled,
      selected: isSelected,
      onTap: enabled ? () => onSelect(date) : null,
      excludeChildren: true,
      child: BondPressable(
        onTap: enabled ? () => onSelect(date) : null,
        borderRadius: BondRadius.r8All,
        child: Container(
          height: BondLayout.controlSm,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: isSelected ? t.accent.base : null,
            borderRadius: BondRadius.r8All,
            border:
                isToday && !isSelected ? Border.all(color: t.accent.base) : null,
          ),
          child: Text(
            '${date.day}',
            style: BondText(t).style(
              BondText.small14,
              isSelected ? BondText.semibold : BondText.regular,
              color: ink,
            ),
          ),
        ),
      ),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({
    required this.icon,
    required this.label,
    required this.onPressed,
    required this.semanticsId,
  });

  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    return BondPressable(
      onTap: onPressed,
      semanticLabel: label,
      semanticsId: semanticsId,
      borderRadius: BondRadius.r8All,
      minSize: BondLayout.controlSm,
      child: Icon(icon,
          size: BondLayout.icon, color: BondTokens.of(context).muted),
    );
  }
}

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
