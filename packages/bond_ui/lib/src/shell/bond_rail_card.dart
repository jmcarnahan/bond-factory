import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// A card for the right rail (people, notes, a photo, a summary). Fills the
/// width it is given; the rail sets the width.
class BondRailCard extends StatelessWidget {
  const BondRailCard({super.key, this.title, this.trailing, required this.child});

  final String? title;
  final Widget? trailing;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      padding: BondSpace.all20,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: t.shape.r16All,
        border: Border.all(color: t.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title != null) ...[
            Row(
              children: [
                Expanded(
                  child: Semantics(
                    header: true,
                    child: Text(title!, style: BondText(t).style(BondText.lead18, BondText.semibold, tight: true)),
                  ),
                ),
                ?trailing,
              ],
            ),
            BondSpace.h16,
          ],
          child,
        ],
      ),
    );
  }
}
