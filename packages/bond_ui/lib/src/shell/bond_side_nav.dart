import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../semantics.dart';
import '../tokens/tokens.dart';
import 'bond_side_nav_item.dart';

/// The office sidebar: wordmark, grouped destinations with section labels
/// (collapsible inline), [footerItems], and a [userCard] slot at the bottom.
///
/// The current place is the plain string [selectedId], compared with each
/// destination's id; the nav imports no router. [rail] draws icons only.
///
/// While [userCardExpanded] is true the destinations, footer items and card
/// scroll together as one column (scrolled to the card when it opens), so an
/// open account card never pushes the nav out of reach on a short window.
class BondSideNav extends StatefulWidget {
  const BondSideNav({
    super.key,
    required this.groups,
    required this.selectedId,
    required this.onSelected,
    this.userCard,
    this.footerItems = const [],
    this.brand = 'Bond',
    this.rail = false,
    this.userCardExpanded = false,
  });

  final List<BondNavGroup> groups;
  final String? selectedId;
  final ValueChanged<String> onSelected;
  final Widget? userCard;

  /// Destinations pinned above the user card (Reports, Settings).
  final List<BondNavDestination> footerItems;
  final String brand;

  /// Icons only, for a window too narrow for the full sidebar.
  final bool rail;

  /// The [userCard] is open: the whole region below the wordmark scrolls.
  final bool userCardExpanded;

  @override
  State<BondSideNav> createState() => _BondSideNavState();
}

class _BondSideNavState extends State<BondSideNav> {
  final ScrollController _whole = ScrollController();
  // Folded state is keyed by a group's identity (semanticsId, else label), so
  // groups inserted, removed or reordered by the app keep their own state.
  // A collapsible group with neither falls back to its index.
  final Set<String> _folded = {};
  final Set<String> _known = {};

  static String _key(BondNavGroup g, int i) => g.semanticsId ?? g.label ?? '#$i';

  /// Starts new groups folded when asked to and forgets groups that are gone.
  void _sync() {
    final live = <String>{};
    for (var i = 0; i < widget.groups.length; i++) {
      final g = widget.groups[i];
      if (!g.collapsible) continue;
      final k = _key(g, i);
      live.add(k);
      if (_known.add(k) && !g.startsExpanded) _folded.add(k);
    }
    _known.retainWhere(live.contains);
    _folded.retainWhere(live.contains);
  }

  /// Opens the folded group that holds the selected destination.
  void _revealSelected() {
    final id = widget.selectedId;
    if (id == null) return;
    for (var i = 0; i < widget.groups.length; i++) {
      final g = widget.groups[i];
      if (g.collapsible && g.items.any((d) => d.id == id)) _folded.remove(_key(g, i));
    }
  }

  @override
  void initState() {
    super.initState();
    _sync();
    _revealSelected();
  }

  @override
  void didUpdateWidget(BondSideNav old) {
    super.didUpdateWidget(old);
    _sync();
    if (widget.selectedId != old.selectedId) _revealSelected();
    if (widget.userCardExpanded && !old.userCardExpanded) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _whole.hasClients) _whole.jumpTo(_whole.position.maxScrollExtent);
      });
    }
  }

  @override
  void dispose() {
    _whole.dispose();
    super.dispose();
  }

  Widget _tile(BondNavDestination d) => BondNavTile(
        destination: d,
        active: widget.selectedId == d.id,
        rail: widget.rail,
        onTap: () => widget.onSelected(d.id),
      );

  Widget _header(BuildContext context, int i) {
    final g = widget.groups[i];
    final t = BondTokens.of(context);
    final style = BondText(t).style(BondText.small14, BondText.medium, color: t.muted);
    const pad = EdgeInsets.fromLTRB(BondSpace.s12, 0, BondSpace.s12, BondSpace.s4);
    if (!g.collapsible) return Padding(padding: pad, child: Text(g.label!, style: style));
    final key = _key(g, i);
    final open = !_folded.contains(key);
    void toggle() => setState(() => open ? _folded.add(key) : _folded.remove(key));
    return bondSemantics(
      id: g.semanticsId,
      label: g.label,
      button: true,
      expanded: open,
      onTap: toggle,
      excludeChildren: true,
      child: BondPressable(
        onTap: toggle,
        child: Padding(
          padding: pad.copyWith(top: BondSpace.s4),
          child: Row(
            children: [
              Expanded(child: Text(g.label!, style: style)),
              Icon(open ? Icons.expand_less : Icons.expand_more, size: BondLayout.icon, color: t.muted),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _groupWidgets(BuildContext context) {
    final rail = widget.rail;
    final groups = widget.groups;
    return [
      for (var i = 0; i < groups.length; i++) ...[
        if (i > 0) rail ? Divider(color: BondTokens.of(context).line) : BondSpace.h16,
        if (!rail && groups[i].label != null) _header(context, i),
        if (rail || !groups[i].collapsible || !_folded.contains(_key(groups[i], i))) for (final d in groups[i].items) _tile(d),
      ],
    ];
  }

  List<Widget> _footer(BuildContext context) => [
        for (final d in widget.footerItems) _tile(d),
        if (widget.footerItems.isNotEmpty) ...[BondSpace.h8, Divider(color: BondTokens.of(context).line)],
        if (widget.userCard != null) ...[BondSpace.h12, widget.userCard!],
      ];

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final rail = widget.rail;
    final whole = widget.userCardExpanded && widget.userCard != null;
    final brand = widget.brand;
    return Container(
      width: rail ? BondLayout.sidebarRail : BondLayout.sidebar,
      decoration: BoxDecoration(color: t.surface, border: Border(right: BorderSide(color: t.line))),
      padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12, vertical: BondSpace.s24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: BondSpace.s12),
            child: Text(
              rail && brand.isNotEmpty ? brand.substring(0, 1) : brand,
              textAlign: rail ? TextAlign.center : TextAlign.start,
              style: BondText(t).title,
            ),
          ),
          BondSpace.h24,
          if (whole)
            Expanded(
              child: SingleChildScrollView(
                key: const ValueKey('bond-side-nav-whole-scroll'),
                controller: _whole,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [..._groupWidgets(context), BondSpace.h16, ..._footer(context)],
                ),
              ),
            )
          else ...[
            Expanded(
              child: SingleChildScrollView(
                key: const ValueKey('bond-side-nav-scroll'),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: _groupWidgets(context)),
              ),
            ),
            ..._footer(context),
          ],
        ],
      ),
    );
  }
}
