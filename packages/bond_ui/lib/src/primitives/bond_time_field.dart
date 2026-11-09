import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../labels.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_segmented.dart';
import 'bond_text_field.dart';

/// A time of day, no date: [hour24] 0-23 and [minute] 0-59.
@immutable
class BondTime {
  const BondTime({required this.hour24, required this.minute})
      : assert(hour24 >= 0 && hour24 < 24),
        assert(minute >= 0 && minute < 60);

  /// Builds from a clock-face hour (1-12) and AM/PM.
  factory BondTime.from12(int hour12, int minute, {required bool pm}) =>
      BondTime(hour24: (hour12 % 12) + (pm ? 12 : 0), minute: minute);

  final int hour24;
  final int minute;

  /// 1-12 as read on a clock face.
  int get hour12 => hour24 % 12 == 0 ? 12 : hour24 % 12;

  bool get isPm => hour24 >= 12;

  @override
  bool operator ==(Object other) =>
      other is BondTime && other.hour24 == hour24 && other.minute == minute;

  @override
  int get hashCode => Object.hash(hour24, minute);

  @override
  String toString() =>
      'BondTime($hour24:${minute.toString().padLeft(2, '0')})';
}

/// Inline time entry: an hour box (1-12), a minute box (00-59) and an AM/PM
/// switch, all in the page. It never opens a picker or any dialog.
///
/// Typing something that is not a valid hour or minute (empty, 0, 13, 75)
/// keeps the last valid value and reports nothing, but the box says so under
/// itself and [onValidChanged] reports false. Leaving the box puts the last
/// valid value back.
///
/// With [semanticsId]: `'<id>-hour'`, `'<id>-minute'`, `'<id>-meridiem-am'`
/// and `'<id>-meridiem-pm'`.
class BondTimeField extends StatefulWidget {
  const BondTimeField({
    super.key,
    required this.value,
    required this.onChanged,
    this.label,
    this.enabled = true,
    this.onValidChanged,
    this.semanticsId,
  });

  final BondTime value;
  final ValueChanged<BondTime> onChanged;
  final String? label;
  final bool enabled;

  /// Called with false while either box holds something that is not a valid
  /// time, and with true when both are fine again (so a caller can hold back
  /// Save). Until it is fixed or the box loses focus, [onChanged] is not
  /// called.
  final ValueChanged<bool>? onValidChanged;
  final String? semanticsId;

  @override
  State<BondTimeField> createState() => _BondTimeFieldState();
}

class _BondTimeFieldState extends State<BondTimeField> {
  late final TextEditingController _hour =
      TextEditingController(text: '${widget.value.hour12}');
  late final TextEditingController _minute = TextEditingController(
      text: widget.value.minute.toString().padLeft(2, '0'));

  /// The last value this field reported or was given.
  late BondTime _last = widget.value;

  final FocusNode _hourFocus = FocusNode();
  final FocusNode _minuteFocus = FocusNode();
  bool _hourBad = false;
  bool _minuteBad = false;

  @override
  void initState() {
    super.initState();
    _hourFocus.addListener(() => _blur(_hourFocus));
    _minuteFocus.addListener(() => _blur(_minuteFocus));
  }

  /// A box that loses focus while invalid goes back to the last valid value.
  void _blur(FocusNode node) {
    if (node.hasFocus || !mounted) return;
    final wasValid = _valid;
    setState(() {
      if (node == _hourFocus && _hourBad) {
        _hour.text = '${_last.hour12}';
        _hourBad = false;
      }
      if (node == _minuteFocus && _minuteBad) {
        _minute.text = _last.minute.toString().padLeft(2, '0');
        _minuteBad = false;
      }
    });
    _notifyValid(wasValid);
  }

  bool get _valid => !_hourBad && !_minuteBad;

  void _notifyValid(bool before) {
    if (before != _valid) widget.onValidChanged?.call(_valid);
  }

  @override
  void dispose() {
    _hourFocus.dispose();
    _minuteFocus.dispose();
    _hour.dispose();
    _minute.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(BondTimeField old) {
    super.didUpdateWidget(old);
    if (widget.value != _last) {
      // Changed from outside: show it.
      _last = widget.value;
      final before = _valid;
      _hour.text = '${_last.hour12}';
      _minute.text = _last.minute.toString().padLeft(2, '0');
      _hourBad = false;
      _minuteBad = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _notifyValid(before);
      });
    }
  }

  void _emit(BondTime t) {
    if (t == _last) return;
    _last = t;
    widget.onChanged(t);
  }

  void _typedHour(String text) {
    final before = _valid;
    final h = int.tryParse(text);
    if (h == null || h < 1 || h > 12) {
      setState(() => _hourBad = true);
      _notifyValid(before);
      return;
    }
    setState(() => _hourBad = false);
    _notifyValid(before);
    _emit(BondTime.from12(h, _last.minute, pm: _last.isPm));
  }

  void _typedMinute(String text) {
    final before = _valid;
    final m = int.tryParse(text);
    if (m == null || m < 0 || m > 59) {
      setState(() => _minuteBad = true);
      _notifyValid(before);
      return;
    }
    setState(() => _minuteBad = false);
    _notifyValid(before);
    _emit(BondTime(hour24: _last.hour24, minute: m));
  }

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final labels = BondLabels.of(context);
    final id = widget.semanticsId;
    final digits = <TextInputFormatter>[
      FilteringTextInputFormatter.digitsOnly,
      LengthLimitingTextInputFormatter(2),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.label != null) ...[
          Text(widget.label!,
              style: BondText(t).style(BondText.small14, BondText.semibold)),
          BondSpace.h4,
        ],
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              flex: 2,
              child: BondTextField(
                controller: _hour,
                focusNode: _hourFocus,
                errorText: _hourBad ? labels.invalidTime : null,
                label: labels.hour,
                keyboardType: TextInputType.number,
                inputFormatters: digits,
                textAlign: TextAlign.center,
                enabled: widget.enabled,
                onChanged: _typedHour,
                semanticsId: id == null ? null : bondSemanticsOption(id, 'hour'),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  BondSpace.s8, 0, BondSpace.s8, BondSpace.s12),
              child: Text(':',
                  style: BondText(t)
                      .style(BondText.lead18, BondText.semibold)),
            ),
            Expanded(
              flex: 2,
              child: BondTextField(
                controller: _minute,
                focusNode: _minuteFocus,
                errorText: _minuteBad ? labels.invalidTime : null,
                label: labels.minute,
                keyboardType: TextInputType.number,
                inputFormatters: digits,
                textAlign: TextAlign.center,
                enabled: widget.enabled,
                onChanged: _typedMinute,
                semanticsId:
                    id == null ? null : bondSemanticsOption(id, 'minute'),
              ),
            ),
            BondSpace.w12,
            Expanded(
              flex: 3,
              child: Padding(
                padding: const EdgeInsets.only(bottom: BondSpace.s4),
                child: BondSegmented<String>(
                  expand: true,
                  segments: [
                    BondSegment('am', labels.am),
                    BondSegment('pm', labels.pm),
                  ],
                  value: _last.isPm ? 'pm' : 'am',
                  semanticsId:
                      id == null ? null : bondSemanticsOption(id, 'meridiem'),
                  onChanged: (v) {
                    if (!widget.enabled) return;
                    _emit(BondTime.from12(_last.hour12, _last.minute,
                        pm: v == 'pm'));
                  },
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
