import 'package:flutter/material.dart';

import '../primitives/bond_segmented.dart';
import '../tokens/tokens.dart';

/// One version of a message, for example one language.
class BondMessageVariant {
  const BondMessageVariant({required this.id, required this.label, required this.body});

  final String id;

  /// The switch label ("English").
  final String label;
  final String body;
}

/// A message as the recipient got it: a switch between its [variants]
/// (languages, channels), the body as sent, and an optional "Sent 5:00 PM"
/// line the caller wrote.
class BondMessagePreview extends StatelessWidget {
  const BondMessagePreview({
    super.key,
    required this.variants,
    required this.selectedId,
    required this.onSelected,
    this.sentLabel,
    this.semanticsId,
  });

  final List<BondMessageVariant> variants;
  final String selectedId;
  final ValueChanged<String> onSelected;
  final String? sentLabel;

  /// Prefix for the switch options: each is `<semanticsId>-<variant id>`.
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    BondMessageVariant? current;
    for (final v in variants) {
      if (v.id == selectedId) current = v;
    }
    current ??= variants.isEmpty ? null : variants.first;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: BondSegmented<String>(
            segments: [for (final v in variants) BondSegment(v.id, v.label)],
            value: current?.id ?? selectedId,
            onChanged: onSelected,
            semanticsId: semanticsId,
          ),
        ),
        BondSpace.h12,
        Container(
          key: const ValueKey('bond-message-body'),
          padding: BondSpace.all16,
          decoration: BoxDecoration(
            color: t.ground,
            borderRadius: t.shape.r12All,
            border: Border.all(color: t.line),
          ),
          child: SelectableText(current?.body ?? '', style: text.small),
        ),
        if (sentLabel != null && sentLabel!.isNotEmpty) ...[
          BondSpace.h8,
          Text(sentLabel!, style: text.label),
        ],
      ],
    );
  }
}
