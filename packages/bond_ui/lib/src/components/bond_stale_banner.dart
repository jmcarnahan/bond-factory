import 'package:flutter/material.dart';

import '../primitives/bond_button.dart';
import '../tokens/tokens.dart';
import '../labels.dart';

/// "Not updated since 11:42" with a retry button, in the page flow. Shown above
/// data that is still on screen after a refresh failed, so old data never looks
/// fresh. [asOf] null says "Not updated yet".
///
/// The widget never formats a time or reads a clock: [formatTime] turns
/// [asOf] into words in the person's language.
class BondStaleBanner extends StatelessWidget {
  const BondStaleBanner({
    super.key,
    required this.asOf,
    required this.onRetry,
    required this.formatTime,
    this.semanticsId = 'stale-banner',
  });

  final DateTime? asOf;
  final VoidCallback onRetry;
  final String Function(DateTime) formatTime;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final at = asOf;
    final labels = BondLabels.of(context);
    final words = at == null ? labels.staleUnknown : '${labels.staleSince} ${formatTime(at)}';
    return Semantics(
      identifier: semanticsId,
      container: true,
      explicitChildNodes: true,
      child: Container(
        padding: BondSpace.all12,
        decoration: BoxDecoration(
          color: t.caution.wash,
          borderRadius: t.shape.r12All,
          border: Border.all(color: t.caution.soft),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              liveRegion: true,
              child: Text(words, style: BondText(t).style(BondText.small14, BondText.medium)),
            ),
            BondSpace.h8,
            BondButton(
              label: labels.retry,
              variant: BondButtonVariant.secondary,
              onPressed: onRetry,
              semanticsId: semanticsId == null ? null : '$semanticsId-retry',
            ),
          ],
        ),
      ),
    );
  }
}
