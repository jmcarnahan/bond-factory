import 'package:bond_connections/bond_connections.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The inline notice shown after the browser comes back from the provider:
/// positive for a connection made, danger (with the reason in plain words)
/// for an error. Not a dialog; it sits in the page flow.
class BondConnectionReturnBanner extends StatelessWidget {
  const BondConnectionReturnBanner(
    this.result, {
    super.key,
    this.labels = const ConnectionLabels(),
    this.onDismiss,
    this.semanticsId,
  });

  final ConnectionReturn result;
  final ConnectionLabels labels;
  final VoidCallback? onDismiss;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final error = result.isError;
    return BondBanner(
      title: error ? labels.errorTitleFor(result.provider) : labels.connectedTitleFor(result.provider),
      message: error ? labels.reasonText(result.reason) : null,
      tone: error ? BondToneRole.danger : BondToneRole.positive,
      onDismiss: onDismiss,
      dismissLabel: labels.dismiss,
      semanticsId: semanticsId,
    );
  }
}
