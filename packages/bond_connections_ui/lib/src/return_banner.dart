import 'package:bond_connections/bond_connections.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

/// The inline notice shown after the browser comes back from the provider:
/// positive for a connection made, danger (with the reason in plain words)
/// for an error. Not a dialog; it sits in the page flow.
///
/// It is drawn here, not with `BondBanner`, so the text can be one semantics
/// node: with [semanticsId] that node is `<id>` and its label is the title and
/// message (a walk reads labels, not identifiers); it is a live region. The
/// dismiss button is its own node, `<id>-dismiss`. The text is exposed once.
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
    final title = error ? labels.errorTitleFor(result.provider) : labels.connectedTitleFor(result.provider);
    final message = error ? labels.reasonText(result.reason) : null;
    final t = BondTokens.of(context);
    final text = BondText(t);
    final c = t.colorsFor(error ? BondToneRole.danger : BondToneRole.positive);
    final id = semanticsId;
    return Container(
      padding: BondSpace.all16,
      decoration: BoxDecoration(
        color: c.background,
        borderRadius: t.shape.r12All,
        border: Border.all(color: c.border),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(error ? Icons.error_outline : Icons.check_circle_outline, size: BondLayout.icon, color: c.foreground),
        BondSpace.w12,
        Expanded(
          child: Semantics(
            identifier: id,
            label: message == null ? title : '$title. $message',
            container: true,
            liveRegion: true,
            excludeSemantics: true,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: text.style(BondText.base16, BondText.semibold, color: c.foreground)),
              if (message != null) Text(message, style: text.small),
            ]),
          ),
        ),
        if (onDismiss != null)
          BondIconButton(
            icon: Icons.close,
            label: labels.dismiss,
            onPressed: onDismiss,
            color: c.foreground,
            semanticsId: id == null ? null : '$id-dismiss',
          ),
      ]),
    );
  }
}
