import 'package:bond_connections/bond_connections.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'connection_card.dart';

/// A [BondConnectionCard] per status, one under the other. The callbacks get
/// the provider id. An empty list shows an inline empty state.
class BondConnectionsList extends StatelessWidget {
  const BondConnectionsList({
    super.key,
    required this.statuses,
    this.labels = const ConnectionLabels(),
    this.onConnect,
    this.onReconnect,
    this.onDisconnect,
    this.logoFor,
    this.formatDate,
    this.busyProvider,
    this.semanticsId,
  });

  final List<ConnectionStatus> statuses;
  final ConnectionLabels labels;
  final void Function(String provider)? onConnect;
  final void Function(String provider)? onReconnect;
  final void Function(String provider)? onDisconnect;

  /// The mark for a provider id; null for none.
  final Widget? Function(String provider)? logoFor;
  final String Function(DateTime)? formatDate;

  /// The provider with a request in flight; its buttons wait.
  final String? busyProvider;

  /// Prefix handed to every card, see [BondConnectionCard.semanticsId].
  final String? semanticsId;

  VoidCallback? _bind(void Function(String)? f, String provider) => f == null ? null : () => f(provider);

  @override
  Widget build(BuildContext context) {
    if (statuses.isEmpty) {
      return BondEmptyState(title: labels.emptyTitle, message: labels.emptyMessage);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      for (var i = 0; i < statuses.length; i++) ...[
        if (i > 0) BondSpace.h12,
        BondConnectionCard(
          key: ValueKey('connection-${statuses[i].provider}'),
          status: statuses[i],
          labels: labels,
          onConnect: _bind(onConnect, statuses[i].provider),
          onReconnect: _bind(onReconnect, statuses[i].provider),
          onDisconnect: _bind(onDisconnect, statuses[i].provider),
          logo: logoFor?.call(statuses[i].provider),
          formatDate: formatDate ?? _defaultDate,
          busy: busyProvider == statuses[i].provider,
          semanticsId: semanticsId,
        ),
      ],
    ]);
  }

  static String _defaultDate(DateTime t) => t.toUtc().toIso8601String().substring(0, 10);
}
