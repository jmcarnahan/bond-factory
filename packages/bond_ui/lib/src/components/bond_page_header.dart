import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../tokens/tokens.dart';
import '../labels.dart';

/// One step in the breadcrumb row. The last crumb (or any without [onTap]) is
/// plain text.
class BondCrumb {
  const BondCrumb(this.label, {this.onTap, this.semanticsId});

  final String label;
  final VoidCallback? onTap;
  final String? semanticsId;
}

/// Title block at the top of a page: optional breadcrumbs and eyebrow, the
/// headline, a subtitle, and [actions] for the page's main controls.
///
/// On a narrow page the actions wrap under the title instead of squeezing both
/// on one line (the width is measured from the space given, not the screen).
class BondPageHeader extends StatelessWidget {
  const BondPageHeader({
    super.key,
    required this.title,
    this.eyebrow,
    this.subtitle,
    this.actions = const [],
    this.breadcrumbs = const [],
  });

  final String title;
  final String? eyebrow;
  final String? subtitle;
  final List<Widget> actions;
  final List<BondCrumb> breadcrumbs;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final labels = BondLabels.of(context);
    final titles = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (breadcrumbs.isNotEmpty) ...[_Crumbs(breadcrumbs, labels.breadcrumbs), BondSpace.h4],
        if (eyebrow != null) Text(eyebrow!, style: text.style(BondText.base16, BondText.regular, color: t.muted)),
        Semantics(container: true, header: true, child: Text(title, style: text.heading)),
        if (subtitle != null) Text(subtitle!, style: text.body),
      ],
    );
    if (actions.isEmpty) return titles;
    final actionRow = Wrap(spacing: BondSpace.s8, runSpacing: BondSpace.s8, children: actions);
    return LayoutBuilder(
      builder: (context, constraints) => constraints.maxWidth < BondLayout.tabletFrom
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [titles, BondSpace.h12, Align(alignment: Alignment.centerLeft, child: actionRow)],
            )
          : Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [Expanded(child: titles), BondSpace.w16, actionRow],
            ),
    );
  }
}

class _Crumbs extends StatelessWidget {
  const _Crumbs(this.crumbs, this.semanticLabel);

  final List<BondCrumb> crumbs;
  final String semanticLabel;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return Semantics(
      container: true,
      label: semanticLabel,
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (var i = 0; i < crumbs.length; i++) ...[
            if (i > 0)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: BondSpace.s4),
                child: Icon(Icons.chevron_right, size: BondLayout.iconSm, color: t.muted),
              ),
            _crumb(context, crumbs[i], last: i == crumbs.length - 1),
          ],
        ],
      ),
    );
  }

  Widget _crumb(BuildContext context, BondCrumb c, {required bool last}) {
    final t = BondTokens.of(context);
    final link = c.onTap != null && !last;
    final words = Text(
      c.label,
      style: BondText(t).style(BondText.small14, last ? BondText.semibold : BondText.medium,
          color: link ? t.accent.press : t.muted),
    );
    if (!link) return Semantics(identifier: c.semanticsId, child: words);
    return BondPressable(
      onTap: c.onTap,
      semanticLabel: c.label,
      semanticsId: c.semanticsId,
      borderRadius: BondRadius.r4All,
      child: Padding(padding: const EdgeInsets.symmetric(vertical: BondSpace.s4), child: words),
    );
  }
}
