import 'dart:async';

import 'package:bond_connections/bond_connections.dart';
import 'package:bond_signin/bond_signin.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// Shows the scope sets the person's role wants that are not granted yet, one
/// row each with an Allow button (`<prefix>.ask-<set id>`). Renders nothing
/// when every set is granted. The ask is the existing connect flow: [onAsk]
/// starts it for the set (`ConnectionsApi.startUrl(..., set: id)`). Inline
/// only; the row is disabled while its ask runs.
class BondScopeAskCard extends StatefulWidget {
  const BondScopeAskCard({
    super.key,
    required this.wanted,
    required this.onAsk,
    required this.labels,
    this.semanticsPrefix = 'sdk.scopes',
  });

  final List<WantedSet> wanted;
  final Future<void> Function(WantedSet set) onAsk;
  final SignInLabels labels;
  final String semanticsPrefix;

  @override
  State<BondScopeAskCard> createState() => _BondScopeAskCardState();
}

class _BondScopeAskCardState extends State<BondScopeAskCard> {
  String? _asking;
  String? _error;

  Future<void> _ask(WantedSet set) async {
    setState(() {
      _asking = set.id;
      _error = null;
    });
    try {
      await widget.onAsk(set);
    } on Object {
      if (mounted) setState(() => _error = widget.labels.messageFor('unknown'));
    } finally {
      if (mounted) setState(() => _asking = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final open = [for (final s in widget.wanted) if (!s.granted) s];
    if (open.isEmpty) return const SizedBox.shrink();
    final t = BondTokens.of(context);
    final text = BondText(t);
    return Container(
      padding: BondSpace.all16,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: t.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(widget.labels.scopesTitle, style: text.bodyStrong),
          if (_error != null) ...[
            BondSpace.h8,
            Semantics(
              identifier: '${widget.semanticsPrefix}.error',
              label: _error,
              container: true,
              liveRegion: true,
              excludeSemantics: true,
              child: Text(_error!, style: text.small.copyWith(color: t.colorsFor(BondToneRole.danger).foreground)),
            ),
          ],
          for (final s in open) ...[
            BondSpace.h12,
            Row(children: [
              Expanded(child: Text(s.label, style: text.small)),
              BondSpace.w12,
              BondButton(
                label: widget.labels.allow,
                variant: BondButtonVariant.secondary,
                loading: _asking == s.id,
                onPressed: _asking == null ? () => unawaited(_ask(s)) : null,
                semanticsId: '${widget.semanticsPrefix}.ask-${s.id}',
              ),
            ]),
          ],
        ],
      ),
    );
  }
}
