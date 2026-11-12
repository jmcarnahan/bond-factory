import 'package:flutter/material.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_date_format.dart';
import 'bond_pressable.dart';

/// A month grid: month header with previous and next, weekday initials and
/// six weeks of day cells. Used by `BondDateField` and by calendar views.
///
/// [firstWeekday] is a `DateTime` weekday (1 Monday to 7 Sunday); the default
/// is Sunday. [dayBuilder] draws a widget under the day number (a count, a
/// dot); null keeps the plain cell. A marker is hidden from screen readers
/// with the cell, so [daySemantics] supplies text appended to the cell's label
/// ("12, 3 overdue"); null or empty adds nothing.
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
    this.dayBuilder,
    this.daySemantics,
    this.firstWeekday = DateTime.sunday,
  });

  final Widget Function(BuildContext context, DateTime day)? dayBuilder;
  final String Function(DateTime day)? daySemantics;
  final int firstWeekday;
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
    // Day arithmetic goes through the DateTime constructor, never Duration:
    // adding 7 absolute days across a DST change duplicates a date.
    final firstOfMonth = DateTime(visibleMonth.year, visibleMonth.month);
    final leadIn = (firstOfMonth.weekday - firstWeekday + 7) % 7;
    final gridStart =
        DateTime(visibleMonth.year, visibleMonth.month, 1 - leadIn);
    // weekdayShort is Monday first.
    final initials = [
      for (var i = 0; i < 7; i++)
        labels.weekdayShort[(firstWeekday - 1 + i) % 7].substring(0, 1),
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
                      dayBuilder: dayBuilder,
                      daySemantics: daySemantics,
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
    this.dayBuilder,
    this.daySemantics,
  });

  final Widget Function(BuildContext context, DateTime day)? dayBuilder;
  final String Function(DateTime day)? daySemantics;
  final DateTime date;
  final DateTime visibleMonth;
  final DateTime? selected;
  final DateTime today;
  final ValueChanged<DateTime> onSelect;
  final bool Function(DateTime day) isSelectable;
  final String? semanticsId;

  String _label() {
    final extra = daySemantics?.call(date);
    return extra == null || extra.isEmpty ? '${date.day}' : '${date.day}, $extra';
  }

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
      label: _label(),
      button: true,
      enabled: enabled,
      selected: isSelected,
      onTap: enabled ? () => onSelect(date) : null,
      excludeChildren: true,
      child: BondPressable(
        onTap: enabled ? () => onSelect(date) : null,
        borderRadius: BondRadius.r8All,
        child: Container(
          constraints: dayBuilder == null
              ? const BoxConstraints.tightFor(height: BondLayout.controlSm)
              : const BoxConstraints(minHeight: BondLayout.controlSm),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: isSelected ? t.accent.base : null,
            borderRadius: BondRadius.r8All,
            border:
                isToday && !isSelected ? Border.all(color: t.accent.base) : null,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${date.day}',
                style: BondText(t).style(
                  BondText.small14,
                  isSelected ? BondText.semibold : BondText.regular,
                  color: ink,
                ),
              ),
              if (dayBuilder != null) dayBuilder!(context, date),
            ],
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
