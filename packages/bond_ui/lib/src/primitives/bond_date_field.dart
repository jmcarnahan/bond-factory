import 'package:flutter/material.dart';

import '../labels.dart';
import '../tokens/tokens.dart';
import 'bond_button.dart';
import 'bond_date_field_calendar.dart';
import 'bond_month_grid.dart';
import 'bond_date_format.dart';
import 'bond_pressable.dart';

/// What the field picks.
enum BondDateMode { date, dateTime, time }

/// A date and/or time field whose picker expands **in flow** beneath it. It
/// never opens a system date or time dialog. In [BondDateMode.date] the value
/// reported is midnight local; in the time modes times snap to 15 minutes.
///
/// [today] is the wall date for the person using the field, passed in from
/// the app clock; the field never reads the device clock itself. A null
/// [value] shows [placeholder] and selects nothing. With [onCleared] the open
/// panel offers a Clear button.
///
/// With [semanticsId]: the field is the id itself, days are
/// `'<id>-day-<yyyy-mm-dd>'`, month paging `'<id>-day-prev'` and
/// `'<id>-day-next'`, time chips `'<id>-time-<hhmm>'`, and the footer buttons
/// `'<id>-today'` and `'<id>-clear'`.
class BondDateField extends StatefulWidget {
  const BondDateField({
    super.key,
    required this.value,
    required this.onChanged,
    required this.today,
    this.onCleared,
    this.label,
    this.placeholder,
    this.mode = BondDateMode.date,
    this.enabled = true,
    this.firstDate,
    this.lastDate,
    this.initiallyOpen = false,
    this.dayStartHour = 6,
    this.dayEndHour = 20,
    this.semanticsId,
  });

  final String? label;
  final String? placeholder;
  final DateTime? value;
  final ValueChanged<DateTime> onChanged;
  final VoidCallback? onCleared;
  final DateTime today;
  final BondDateMode mode;
  final bool enabled;

  /// Days before this are dimmed and not selectable (compared by date).
  final DateTime? firstDate;

  /// Days after this are dimmed and not selectable (compared by date).
  final DateTime? lastDate;
  final bool initiallyOpen;

  /// Range of the 15-minute time chips.
  final int dayStartHour;
  final int dayEndHour;
  final String? semanticsId;

  @override
  State<BondDateField> createState() => _BondDateFieldState();
}

class _BondDateFieldState extends State<BondDateField> {
  late bool _open = widget.initiallyOpen;

  /// First of the month the grid shows, independent of the selection so the
  /// person can page around without committing to a date.
  late DateTime _visibleMonth = _monthOf(widget.value ?? widget.today);

  static DateTime _monthOf(DateTime d) => DateTime(d.year, d.month);

  @override
  void didUpdateWidget(BondDateField old) {
    super.didUpdateWidget(old);
    final v = widget.value;
    final o = old.value;
    if (v != null && (o == null || !BondDateFormat.sameDay(o, v))) {
      _visibleMonth = _monthOf(v);
    } else if (v == null &&
        !BondDateFormat.sameDay(old.today, widget.today)) {
      // Nothing picked: follow the app clock's day.
      _visibleMonth = _monthOf(widget.today);
    }
  }

  void _shiftMonth(int delta) => setState(() {
        _visibleMonth =
            DateTime(_visibleMonth.year, _visibleMonth.month + delta);
      });

  bool _isSelectable(DateTime day) {
    final d = DateTime(day.year, day.month, day.day);
    final first = widget.firstDate;
    if (first != null &&
        d.isBefore(DateTime(first.year, first.month, first.day))) {
      return false;
    }
    final last = widget.lastDate;
    if (last != null && d.isAfter(DateTime(last.year, last.month, last.day))) {
      return false;
    }
    return true;
  }

  void _selectDay(DateTime day) {
    final v = widget.value;
    // With no value yet, a day alone is reported at midnight and no time chip
    // is lit: "no time answered" until a chip is tapped.
    final withTime = widget.mode == BondDateMode.dateTime && v != null
        ? DateTime(day.year, day.month, day.day, v.hour, v.minute)
        : DateTime(day.year, day.month, day.day);
    widget.onChanged(withTime);
    // Date-only closes; date plus time stays open for the time chips.
    if (widget.mode == BondDateMode.date) setState(() => _open = false);
  }

  void _selectTime(int hour, int minute) {
    final v = widget.value ?? widget.today;
    widget.onChanged(DateTime(v.year, v.month, v.day, hour, minute));
    setState(() => _open = false);
  }

  void _clear() {
    widget.onCleared?.call();
    setState(() => _open = false);
  }

  String _display(BondLabels l) {
    final v = widget.value;
    if (v == null) return widget.placeholder ?? '';
    return switch (widget.mode) {
      BondDateMode.date => BondDateFormat.date(l, v),
      BondDateMode.dateTime =>
        '${BondDateFormat.date(l, v)} · ${BondDateFormat.time(l, v)}',
      BondDateMode.time => BondDateFormat.time(l, v),
    };
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final labels = BondLabels.of(context);
    final id = widget.semanticsId;
    final showDays = widget.mode != BondDateMode.time;
    final showTimes = widget.mode != BondDateMode.date;
    final shown = _display(labels);
    final hasValue = widget.value != null;

    final field = BondPressable(
      onTap: widget.enabled ? () => setState(() => _open = !_open) : null,
      borderRadius: t.shape.r12All,
      semanticsId: id,
      semanticLabel: widget.label == null ? shown : '${widget.label}: $shown',
      child: Container(
        height: BondLayout.control,
        padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12),
        decoration: BoxDecoration(
          color: widget.enabled ? t.surface : t.ground,
          borderRadius: t.shape.r12All,
          border: Border.all(
            color: _open ? t.accent.base : t.lineStrong,
            width: _open ? BondLayout.rule : BondLayout.hairline,
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                shown,
                style: text.style(BondText.base16, BondText.regular,
                    color: widget.enabled && hasValue ? t.ink : t.muted),
              ),
            ),
            Icon(
              _open
                  ? Icons.keyboard_arrow_up
                  : (showDays ? Icons.calendar_today_outlined : Icons.schedule),
              size: BondLayout.iconSm,
              color: t.muted,
            ),
          ],
        ),
      ),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.label != null) ...[
          Text(widget.label!,
              style: text.style(BondText.small14, BondText.semibold)),
          BondSpace.h4,
        ],
        field,
        if (_open) ...[
          BondSpace.h8,
          if (showDays)
            BondMonthGrid(
              visibleMonth: _visibleMonth,
              selected: widget.value,
              today: widget.today,
              onPrevious: () => _shiftMonth(-1),
              onNext: () => _shiftMonth(1),
              onSelect: _selectDay,
              isSelectable: _isSelectable,
              semanticsId: id == null ? null : '$id-day',
            ),
          if (showDays && showTimes) BondSpace.h8,
          if (showTimes)
            BondTimeChips(
              selected: widget.value,
              startHour: widget.dayStartHour,
              endHour: widget.dayEndHour,
              onSelect: _selectTime,
              semanticsId: id == null ? null : '$id-time',
            ),
          if (showDays || (widget.onCleared != null && hasValue))
            Wrap(
              children: [
                if (showDays)
                  BondButton(
                    label: labels.today,
                    variant: BondButtonVariant.quiet,
                    onPressed: _isSelectable(widget.today)
                        ? () => _selectDay(widget.today)
                        : null,
                    semanticsId: id == null ? null : '$id-today',
                  ),
                if (widget.onCleared != null && hasValue)
                  BondButton(
                    label: labels.clear,
                    variant: BondButtonVariant.quiet,
                    onPressed: _clear,
                    semanticsId: id == null ? null : '$id-clear',
                  ),
              ],
            ),
        ],
      ],
    );
  }
}
