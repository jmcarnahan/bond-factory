import 'package:flutter/material.dart';

import '../semantics.dart';
import '../tokens/tokens.dart';

/// A status: label, tone and optional icon. A null [tone] is neutral.
class BondStatus {
  const BondStatus(this.label, {this.tone, this.icon});

  /// From the wire form `{label, tone}`. A positive status gets a check.
  factory BondStatus.fromWire(String label, String tone) {
    final role = bondToneFromName(tone);
    return BondStatus(
      label,
      tone: role,
      icon: role == BondToneRole.positive ? Icons.check : null,
    );
  }

  final String label;
  final BondToneRole? tone;
  final IconData? icon;
}

/// Maps a server tone name to a role. Anything unknown, `neutral` included,
/// is null (neutral). `red` is accepted as an alias of `danger`.
BondToneRole? bondToneFromName(String name) => switch (name) {
      'positive' => BondToneRole.positive,
      'caution' => BondToneRole.caution,
      'danger' || 'red' => BondToneRole.danger,
      'info' => BondToneRole.info,
      'accent' => BondToneRole.accent,
      _ => null,
    };

/// A small non-interactive pill showing a [BondStatus]. The label wraps
/// instead of being cut.
class BondStatusChip extends StatelessWidget {
  const BondStatusChip(this.status, {super.key, this.semanticsId});

  final BondStatus status;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final c = t.colorsFor(status.tone);
    final chip = Container(
      padding: const EdgeInsets.symmetric(
          horizontal: BondSpace.s8, vertical: BondSpace.s4),
      decoration: BoxDecoration(
        color: c.background,
        borderRadius: BondRadius.pillAll,
        border: Border.all(color: c.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (status.icon != null) ...[
            Icon(status.icon, size: BondLayout.iconSm, color: c.foreground),
            BondSpace.w4,
          ],
          Flexible(
            child: Text(
              status.label,
              style: BondText(t).style(BondText.label13, BondText.semibold,
                  color: c.foreground),
            ),
          ),
        ],
      ),
    );
    return bondSemantics(id: semanticsId, child: chip);
  }
}
