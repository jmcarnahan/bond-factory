import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

final RegExp _hhmm = RegExp(r'^([01]?\d|2[0-3]):([0-5]\d)$');

/// "8:00" becomes "08:00"; null when the text is not a time of day.
String? _normal(String s) {
  final m = _hhmm.firstMatch(s.trim());
  return m == null ? null : '${m[1]!.padLeft(2, '0')}:${m[2]}';
}

/// The per-person task settings: start and end of the work day (HH:MM), the
/// lead in minutes, the zone (read only) and one sentence that states the
/// quiet hours the two times imply. Save calls [onSubmit] only for valid
/// input; problems show inline (a time must read HH:MM, the start and the end
/// must differ, the lead is a whole number of minutes 0 to 10080).
///
/// With [semanticsPrefix]: `<prefix>.settings-start`, `-end`, `-lead`,
/// `-quiet`, `-save`.
class BondTaskSettingsForm extends StatefulWidget {
  const BondTaskSettingsForm({
    super.key,
    required this.settings,
    required this.onSubmit,
    this.busy = false,
    this.labels = const SettingsLabels(),
    this.semanticsPrefix,
  });

  final TaskSettings settings;
  final ValueChanged<TaskSettingsPatch> onSubmit;
  final bool busy;
  final SettingsLabels labels;
  final String? semanticsPrefix;

  @override
  State<BondTaskSettingsForm> createState() => _BondTaskSettingsFormState();
}

class _BondTaskSettingsFormState extends State<BondTaskSettingsForm> {
  late final TextEditingController _start;
  late final TextEditingController _end;
  late final TextEditingController _lead;

  /// True once the person typed; a reload of [BondTaskSettingsForm.settings] then keeps their text.
  bool _edited = false;
  @override
  void initState() {
    super.initState();
    _start = TextEditingController(text: widget.settings.startOfDay);
    _end = TextEditingController(text: widget.settings.endOfDay);
    _lead = TextEditingController(text: '${widget.settings.leadMinutes}');
  }

  @override
  void didUpdateWidget(BondTaskSettingsForm old) {
    super.didUpdateWidget(old);
    final a = old.settings, b = widget.settings;
    final changed = a.startOfDay != b.startOfDay || a.endOfDay != b.endOfDay || a.leadMinutes != b.leadMinutes;
    // The page may build the form before the settings load; take the loaded values unless edited.
    if (changed && !_edited) {
      _start.text = b.startOfDay;
      _end.text = b.endOfDay;
      _lead.text = '${b.leadMinutes}';
    }
  }

  void _typed() => setState(() => _edited = true);

  @override
  void dispose() {
    _start.dispose();
    _end.dispose();
    _lead.dispose();
    super.dispose();
  }

  String? _id(String part) => widget.semanticsPrefix == null ? null : '${widget.semanticsPrefix}.settings-$part';

  int? get _leadValue {
    final n = int.tryParse(_lead.text.trim());
    return n != null && n >= 0 && n <= 10080 ? n : null;
  }

  void _save() {
    final s = _normal(_start.text);
    final e = _normal(_end.text);
    final lead = _leadValue;
    if (s == null || e == null || s == e || lead == null) return;
    widget.onSubmit(TaskSettingsPatch(startOfDay: s, endOfDay: e, leadMinutes: lead));
  }

  @override
  Widget build(BuildContext context) {
    final l = widget.labels;
    final t = BondTokens.of(context);
    final text = BondText(t);
    final s = _normal(_start.text);
    final e = _normal(_end.text);
    final same = s != null && s == e;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(l.timeZone, style: text.smallStrong),
        Text(widget.settings.timeZone ?? '-', style: text.body.copyWith(color: t.muted)),
        BondSpace.h12,
        BondTextField(
          controller: _start,
          label: l.workDayStart,
          keyboardType: TextInputType.datetime,
          errorText: s == null ? l.invalidTime : null,
          onChanged: (_) => _typed(),
          semanticsId: _id('start'),
        ),
        BondSpace.h12,
        BondTextField(
          controller: _end,
          label: l.workDayEnd,
          keyboardType: TextInputType.datetime,
          errorText: e == null ? l.invalidTime : (same ? l.sameTimes : null),
          onChanged: (_) => _typed(),
          semanticsId: _id('end'),
        ),
        BondSpace.h12,
        BondTextField(
          controller: _lead,
          label: '${l.leadMinutes} (${l.minutes})',
          keyboardType: TextInputType.number,
          errorText: _leadValue == null ? l.invalidLead : null,
          onChanged: (_) => _typed(),
          semanticsId: _id('lead'),
        ),
        if (s != null && e != null && !same) ...[
          BondSpace.h12,
          Semantics(
            identifier: _id('quiet'),
            container: true,
            child: Text(l.quietHoursText(s, e), style: text.small.copyWith(color: t.muted)),
          ),
        ],
        for (final w in widget.settings.warnings)
          Padding(
            padding: const EdgeInsets.only(top: BondSpace.s8),
            child: Text(w, style: text.small.copyWith(color: t.danger.press)),
          ),
        BondSpace.h16,
        Align(
          alignment: Alignment.centerLeft,
          child: BondButton(
            label: l.save,
            loading: widget.busy,
            onPressed: widget.busy ? null : _save,
            semanticsId: _id('save'),
          ),
        ),
      ],
    );
  }
}
