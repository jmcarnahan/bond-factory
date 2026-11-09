import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// A column that sits beside the page content (never over it).
class BondRightRail extends StatelessWidget {
  const BondRightRail({
    super.key,
    required this.title,
    required this.child,
    this.width = BondLayout.railWidth,
    this.trailing,
  });

  final String title;
  final Widget child;
  final double width;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Container(
      width: width,
      padding: BondSpace.all20,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r16All,
        border: Border.all(color: t.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(title, style: BondText(t).style(BondText.lead18, BondText.semibold, tight: true)),
                ),
              ),
              ?trailing,
            ],
          ),
          BondSpace.h16,
          child,
        ],
      ),
    );
  }
}
