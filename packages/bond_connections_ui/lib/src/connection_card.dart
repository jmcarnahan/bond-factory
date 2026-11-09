import 'package:bond_connections/bond_connections.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// One provider: name (and an optional logo), a state chip, the account
/// e-mail, the connected date, and the buttons that fit the state.
///
/// - disconnected: Connect
/// - connected: Disconnect (inline two-step confirm, no dialog)
/// - needs reconnect: a hint, Reconnect and Disconnect
///
/// [semanticsId] is a prefix. With `sdk.connections` the elements are
/// `sdk.connections.card-<provider>`, `.state-<provider>`, `.connect-<provider>`,
/// `.reconnect-<provider>` and `.disconnect-<provider>` (the confirm step adds
/// `-confirm` and `-cancel`). A null prefix leaves the card without ids.
class BondConnectionCard extends StatelessWidget {
  const BondConnectionCard({
    super.key,
    required this.status,
    this.labels = const ConnectionLabels(),
    this.onConnect,
    this.onReconnect,
    this.onDisconnect,
    this.logo,
    this.formatDate = _isoDate,
    this.busy = false,
    this.semanticsId,
  });

  final ConnectionStatus status;
  final ConnectionLabels labels;

  /// Taps on Connect, Reconnect and (after the confirm step) Disconnect. A
  /// null callback leaves that button out.
  final VoidCallback? onConnect;
  final VoidCallback? onReconnect;
  final VoidCallback? onDisconnect;

  /// The provider's mark, shown before the name.
  final Widget? logo;

  /// How the connected date reads; defaults to `YYYY-MM-DD` (UTC).
  final String Function(DateTime) formatDate;

  /// A request for this provider is in flight: the buttons wait.
  final bool busy;
  final String? semanticsId;

  static String _isoDate(DateTime t) => t.toUtc().toIso8601String().substring(0, 10);

  String? _id(String part) => semanticsId == null ? null : '$semanticsId.$part-${status.provider}';

  BondStatus get _chip => switch (status.phase) {
        ConnectionPhase.connected => BondStatus(labels.stateConnected, tone: BondToneRole.positive, icon: Icons.check),
        ConnectionPhase.needsReconnect => BondStatus(labels.stateNeedsReconnect, tone: BondToneRole.caution),
        ConnectionPhase.disconnected => BondStatus(labels.stateDisconnected),
      };

  @override
  Widget build(BuildContext context) {
    final text = BondText(BondTokens.of(context));
    final state = status.phase;
    final at = status.connectedAt;
    final lines = <String>[
      if (state != ConnectionPhase.disconnected && status.email != null)
        ConnectionLabels.fill(labels.connectedAs, {'email': status.email!}),
      if (state != ConnectionPhase.disconnected && at != null)
        ConnectionLabels.fill(labels.connectedOn, {'date': formatDate(at)}),
    ];
    return BondCard(
      semanticsId: _id('card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            if (logo != null) ...[logo!, BondSpace.w12],
            Expanded(child: Text(labels.providerName(status.provider), style: text.bodyStrong)),
            BondSpace.w8,
            // The identifier node carries the text as its label (a walk reads labels).
            Semantics(
              identifier: _id('state'),
              label: _chip.label,
              excludeSemantics: true,
              child: BondStatusChip(_chip),
            ),
          ]),
          for (final line in lines) ...[BondSpace.h4, Text(line, style: text.small)],
          if (state == ConnectionPhase.needsReconnect) ...[
            BondSpace.h8,
            Text(labels.needsReconnectHint, style: text.small),
          ],
          BondSpace.h12,
          Wrap(spacing: BondSpace.s8, runSpacing: BondSpace.s8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            if (state == ConnectionPhase.disconnected && onConnect != null)
              BondButton(
                label: labels.connect,
                onPressed: busy ? null : onConnect,
                semanticsId: _id('connect'),
              ),
            if (state == ConnectionPhase.needsReconnect && (onReconnect ?? onConnect) != null)
              BondButton(
                label: labels.reconnect,
                onPressed: busy ? null : (onReconnect ?? onConnect),
                semanticsId: _id('reconnect'),
              ),
            if (state != ConnectionPhase.disconnected && onDisconnect != null) _disconnect(),
          ]),
        ],
      ),
    );
  }

  Widget _disconnect() => BondConfirm(
        identity: status.provider,
        semanticsId: _id('disconnect'),
        confirmLabel: labels.disconnect,
        onConfirm: onDisconnect!,
        trigger: (arm) => BondButton(
          label: labels.disconnect,
          variant: BondButtonVariant.secondary,
          onPressed: busy ? null : arm,
          semanticsId: _id('disconnect'),
        ),
      );
}
