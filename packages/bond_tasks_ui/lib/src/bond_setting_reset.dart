import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The line under one task setting: a quiet "Default" hint while the setting follows the app
/// default, or an inline "Reset to default" text control once the person has set it. Nothing shows
/// when [overridden] is null (the server did not say). The control is at least `BondLayout.minTap`
/// high and is named for a screen reader by `SettingsLabels.resetNameFor`.
/// The control is keyed `task-settings-reset-<wireField>` (and carries [semanticsId]).
class BondSettingReset extends StatelessWidget {
  const BondSettingReset({
    super.key,
    required this.wireField,
    required this.overridden,
    required this.onReset,
    this.labels = const SettingsLabels(),
    this.semanticsId,
    this.enabled = true,
  });

  final String wireField;
  /// Null when unknown (an older server): neither the hint nor the control shows.
  final bool? overridden;
  final VoidCallback onReset;
  final SettingsLabels labels;
  final String? semanticsId;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: overridden == null
          ? const SizedBox.shrink()
          : overridden!
          ? BondPressable(
              key: ValueKey('task-settings-reset-$wireField'),
              onTap: enabled ? onReset : null,
              semanticLabel: labels.resetNameFor(wireField),
              semanticsId: semanticsId,
              minSize: BondLayout.minTap,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: BondSpace.s8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  widthFactor: 1,
                  child: Text(
                    labels.resetToDefault,
                    style: BondText(t).small.copyWith(color: enabled ? t.ink : t.muted, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            )
          : Padding(
              padding: const EdgeInsets.only(top: BondSpace.s4),
              child: Text(labels.usingDefault, style: BondText(t).small.copyWith(color: t.muted)),
            ),
    );
  }
}
