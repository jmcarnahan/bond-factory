import 'dart:async';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../todo/todo_alerts.dart';
import '../todo/todo_services.dart';
import 'page_scaffold.dart';

/// The zones the settings page offers.
const List<String> kDemoZones = [
  'America/Los_Angeles',
  'America/Denver',
  'America/Chicago',
  'America/New_York',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Africa/Cairo',
  'Asia/Kolkata',
  'Asia/Tokyo',
  'Australia/Sydney',
  'UTC',
];

/// `GET` and `PUT /tasks/settings`: the work day, the lead and the zone. The form states the quiet
/// hours in words; warnings the server returns show inline. After a save the alerts are planned again.
/// Ids are `sdk.todo.<element>`: `settings-start`, `-end`, `-lead`, `-quiet`, `-save`, `settings-zone`, `zone-state`, `saved` (warnings are shown by the form as plain text), `error`, `alerts-permission`.
class TodoSettingsPage extends StatefulWidget {
  const TodoSettingsPage({super.key, this.services});

  final TodoServices? services;

  @override
  State<TodoSettingsPage> createState() => _TodoSettingsPageState();
}

class _TodoSettingsPageState extends State<TodoSettingsPage> {
  static const String _id = 'sdk.todo';

  late final TodoServices _s = widget.services ?? TodoServices.shared;
  TaskSettings? _settings;
  String? _error;
  String? _saved;
  String? _permission;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      await _s.signIn();
      final settings = await _s.settings.get();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  Future<void> _save(TaskSettingsPatch patch, String saved) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _saved = null;
    });
    try {
      final next = await _s.settings.update(patch);
      if (patch.timeZone != null) _s.zone = next.timeZone ?? patch.timeZone;
      TodoAlerts.updatePrefs(next);
      if (mounted) {
        setState(() {
          _settings = next;
          _saved = saved;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _askPermission() async {
    final ok = await TodoAlerts.requestPermission();
    if (mounted) setState(() => _permission = ok ? 'Phone alerts are allowed' : 'Phone alerts are not allowed');
  }

  @override
  Widget build(BuildContext context) {
    final settings = _settings;
    final text = BondText.of(context);
    final danger = TextStyle(color: BondTokens.of(context).danger.press);
    return DemoScope(
      child: PageFrame(
        title: 'TODO settings',
        children: [
          if (_error != null) labelledText('$_id.error', _error!, danger),
          if (settings == null && _error == null) const BondLoadingState(),
          if (settings != null) ...[
            BondTaskSettingsForm(
              settings: settings,
              busy: _busy,
              semanticsPrefix: _id,
              zoneOptions: kDemoZones,
              onSubmit: (patch) => _save(patch, 'Settings saved'),
            ),
            BondSpace.h8,
            labelledText('$_id.zone-state', 'Zone: ${settings.timeZone ?? 'not set'}', text.small),
            if (_saved != null) ...[BondSpace.h8, labelledText('$_id.saved', _saved!)],
            if (!kIsWeb) ...[
              BondSpace.h24,
              BondButton(
                label: 'Allow phone alerts',
                variant: BondButtonVariant.secondary,
                onPressed: _askPermission,
                semanticsId: '$_id.alerts-permission',
              ),
              if (_permission != null) labelledText('$_id.alerts-state', _permission!),
            ],
          ],
        ],
      ),
    );
  }
}
