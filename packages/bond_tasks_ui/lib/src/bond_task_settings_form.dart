import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_setting_reset.dart';

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
/// Under each setting a quiet "Default" hint shows while it follows the app default; once the
/// person has set it (`settings.overridden`) an inline "Reset to default" control takes its place
/// and sends a patch with that field in `reset`. When the server did not say (`overridden` is null)
/// neither shows. Save sends only the fields that changed or that the person already set, so one
/// Save does not turn every field into a personal setting; with nothing to send it does nothing.
///
/// With [semanticsPrefix]: `<prefix>.settings-start`, `-end`, `-lead`,
/// `-quiet`, `-save`, and `-reset-zone`, `-reset-start`, `-reset-end`, `-reset-lead`.
class BondTaskSettingsForm extends StatefulWidget {
  const BondTaskSettingsForm({
    super.key,
    required this.settings,
    required this.onSubmit,
    this.busy = false,
    this.labels = const SettingsLabels(),
    this.semanticsPrefix,
    this.zoneOptions,
  });

  final TaskSettings settings;
  final ValueChanged<TaskSettingsPatch> onSubmit;
  final bool busy;
  final SettingsLabels labels;
  final String? semanticsPrefix;

  /// IANA zone names to choose from. When given the zone is chosen inline
  /// (search, then pick) and goes out in the patch; null keeps it read-only.
  final List<String>? zoneOptions;

  @override
  State<BondTaskSettingsForm> createState() => _BondTaskSettingsFormState();
}

class _BondTaskSettingsFormState extends State<BondTaskSettingsForm> {
  late final TextEditingController _start;
  late final TextEditingController _end;
  late final TextEditingController _lead;

  /// True once the person typed; a reload of [BondTaskSettingsForm.settings] then keeps their text.
  bool _edited = false;
  String? _zone;

  /// Wire fields whose reset was sent; their text follows the reload that clears them.
  final Set<String> _resetting = {};

  @override
  void initState() {
    super.initState();
    _zone = widget.settings.timeZone;
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
    if (a.timeZone != b.timeZone && !_edited) _zone = b.timeZone;
    // A reset that ended (busy went off) with the field still overridden failed: forget it, so a
    // later reload cannot overwrite what the person types.
    if (old.busy && !widget.busy) {
      _resetting.removeWhere(b.isOverridden);
    }
    for (final f in _resetting.toList()) {
      if (b.isOverridden(f)) continue;
      _resetting.remove(f);
      switch (f) {
        case 'time_zone':
          _zone = b.timeZone;
        case 'start_of_day':
          _start.text = b.startOfDay;
        case 'end_of_day':
          _end.text = b.endOfDay;
        case 'lead_minutes':
          _lead.text = '${b.leadMinutes}';
      }
    }
  }

  void _reset(String field) {
    _resetting.add(field);
    widget.onSubmit(TaskSettingsPatch(reset: {field}));
  }

  Widget _resetFor(String field, String part) => BondSettingReset(
        wireField: field,
        overridden: widget.settings.overriddenKnown ? widget.settings.isOverridden(field) : null,
        onReset: () => _reset(field),
        labels: widget.labels,
        semanticsId: _id('reset-$part'),
        enabled: !widget.busy,
      );

  void _typed(String field) => setState(() {
        _edited = true;
        _resetting.remove(field);
      });

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
    final cur = widget.settings;
    // Only a changed field goes out, or one the person already set: a present field is stored as theirs.
    // A server that does not say what is overridden gets every field, as before.
    bool send(String field, bool changed) => !cur.overriddenKnown || changed || cur.isOverridden(field);
    final sendStart = send('start_of_day', s != (_normal(cur.startOfDay) ?? cur.startOfDay));
    final sendEnd = send('end_of_day', e != (_normal(cur.endOfDay) ?? cur.endOfDay));
    final sendLead = send('lead_minutes', lead != cur.leadMinutes);
    final sendZone = widget.zoneOptions != null && _zone != null && send('time_zone', _zone != cur.timeZone);
    if (!sendStart && !sendEnd && !sendLead && !sendZone) return;
    widget.onSubmit(TaskSettingsPatch(
      startOfDay: sendStart ? s : null,
      endOfDay: sendEnd ? e : null,
      leadMinutes: sendLead ? lead : null,
      timeZone: sendZone ? _zone : null,
    ));
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
        if (widget.zoneOptions == null)
          Text(widget.settings.timeZone ?? '-', style: text.body.copyWith(color: t.muted))
        else
          BondSearchPicker<String>(
            onSearch: (q) async => [
              for (final z in widget.zoneOptions!)
                if (z.toLowerCase().contains(q.toLowerCase())) z,
            ].take(8).toList(),
            labelOf: (z) => z,
            picked: [?_zone],
            onPick: (z) => setState(() {
              _zone = z;
              _edited = true;
              _resetting.remove('time_zone');
            }),
            hint: l.zoneSearchHint,
            semanticsId: _id('zone'),
          ),
        _resetFor('time_zone', 'zone'),
        BondSpace.h12,
        BondTextField(
          controller: _start,
          label: l.workDayStart,
          keyboardType: TextInputType.datetime,
          errorText: s == null ? l.invalidTime : null,
          onChanged: (_) => _typed('start_of_day'),
          semanticsId: _id('start'),
        ),
        _resetFor('start_of_day', 'start'),
        BondSpace.h12,
        BondTextField(
          controller: _end,
          label: l.workDayEnd,
          keyboardType: TextInputType.datetime,
          errorText: e == null ? l.invalidTime : (same ? l.sameTimes : null),
          onChanged: (_) => _typed('end_of_day'),
          semanticsId: _id('end'),
        ),
        _resetFor('end_of_day', 'end'),
        BondSpace.h12,
        BondTextField(
          controller: _lead,
          label: '${l.leadMinutes} (${l.minutes})',
          keyboardType: TextInputType.number,
          errorText: _leadValue == null ? l.invalidLead : null,
          onChanged: (_) => _typed('lead_minutes'),
          semanticsId: _id('lead'),
        ),
        _resetFor('lead_minutes', 'lead'),
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
