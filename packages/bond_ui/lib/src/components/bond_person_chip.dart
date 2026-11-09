import 'package:flutter/material.dart';

import '../primitives/bond_dashed_border.dart';
import '../tokens/tokens.dart';
import '../labels.dart';

/// A pill with a person-coloured dot, like "Alex". With no [slot] it is a
/// dashed outline carrying the "unassigned" label (or [label] when given).
///
/// [slot] is a zero-based index into [BondTokens.personPalette]; a slot past
/// the end of the palette wraps around, so any number of people get a colour.
class BondPersonChip extends StatelessWidget {
  const BondPersonChip({
    super.key,
    this.label,
    this.slot,
    this.semanticsId,
  });

  final String? label;
  final int? slot;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final s = slot;
    final labels = BondLabels.of(context);
    final words = label ?? labels.noPerson;
    const pad = EdgeInsets.symmetric(horizontal: BondSpace.s12, vertical: BondSpace.s4);
    final name = Text(
      words,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: BondText(t).style(BondText.small14, BondText.medium, color: s == null ? t.muted : t.ink),
    );
    final Widget chip = s == null
        ? BondDashedBorder(radius: BondRadius.pill, child: Padding(padding: pad, child: name))
        : Container(
            padding: pad,
            decoration: BoxDecoration(color: t.ground, borderRadius: BondRadius.pillAll),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  key: ValueKey('bond-person-dot-$s'),
                  width: BondLayout.dot,
                  height: BondLayout.dot,
                  decoration: BoxDecoration(color: t.personPalette[s % t.personPalette.length], shape: BoxShape.circle),
                ),
                BondSpace.w8,
                Flexible(child: name),
              ],
            ),
          );
    return Semantics(identifier: semanticsId, label: words, container: true, child: ExcludeSemantics(child: chip));
  }
}
