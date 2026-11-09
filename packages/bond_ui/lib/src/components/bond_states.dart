import 'package:flutter/material.dart';

import '../primitives/bond_button.dart';
import '../tokens/tokens.dart';
import '../labels.dart';

/// Nothing here yet: icon, title, message and an optional action.
class BondEmptyState extends StatelessWidget {
  const BondEmptyState({
    super.key,
    required this.title,
    this.message,
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
    this.actionSemanticsId,
  });

  final String title;
  final String? message;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;
  final String? actionSemanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    return Padding(
      padding: BondSpace.all24,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: BondLayout.iconLg + BondSpace.s8, color: t.lineStrong),
            BondSpace.h12,
            Text(title, textAlign: TextAlign.center, style: text.bodyStrong),
            if (message != null) ...[
              BondSpace.h4,
              Text(message!, textAlign: TextAlign.center, style: text.small),
            ],
            if (actionLabel != null) ...[
              BondSpace.h16,
              BondButton(
                label: actionLabel!,
                variant: BondButtonVariant.secondary,
                onPressed: onAction,
                semanticsId: actionSemanticsId,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A spinner with a short label.
class BondLoadingState extends StatelessWidget {
  const BondLoadingState({super.key, this.label});

  final String? label;

  @override
  Widget build(BuildContext context) {
    final words = label ?? BondLabels.of(context).loading;
    return Padding(
      padding: BondSpace.all24,
      child: Center(
        child: Semantics(
          liveRegion: true,
          label: words,
          child: ExcludeSemantics(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(
                  width: BondLayout.iconLg,
                  height: BondLayout.iconLg,
                  child: CircularProgressIndicator(strokeWidth: BondLayout.rule),
                ),
                BondSpace.h8,
                Text(words, style: BondText.of(context).label),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A failed load, with a retry button when [onRetry] is given.
class BondErrorState extends StatelessWidget {
  const BondErrorState({
    super.key,
    this.message,
    this.onRetry,
    this.semanticsId,
    this.retrySemanticsId,
  });

  final String? message;
  final VoidCallback? onRetry;

  /// Identifier of the message node (the thing a driver asserts on).
  final String? semanticsId;
  final String? retrySemanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final l = BondLabels.of(context);
    return Padding(
      padding: BondSpace.all24,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: BondLayout.iconLg, color: t.danger.press),
            BondSpace.h8,
            Semantics(
              identifier: semanticsId,
              container: true,
              liveRegion: true,
              child: Text(message ?? l.errorTitle, textAlign: TextAlign.center, style: BondText(t).body),
            ),
            if (onRetry != null) ...[
              BondSpace.h16,
              BondButton(
                label: l.retry,
                variant: BondButtonVariant.secondary,
                onPressed: onRetry,
                semanticsId: retrySemanticsId,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
