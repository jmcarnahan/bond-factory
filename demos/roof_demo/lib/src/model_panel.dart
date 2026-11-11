import 'package:flutter/material.dart';

import 'tokens.dart';

/// Inline, in-flow expander with the totals table and the warnings.
class ModelPanel extends StatelessWidget {
  const ModelPanel(this.json, {super.key, this.extraNotes = const []});

  final Map<String, dynamic> json;

  /// Envelope warnings, listed after the model's own.
  final List<String> extraNotes;

  static String _fmt(Object? v) {
    if (v is num) return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);
    return '$v';
  }

  @override
  Widget build(BuildContext context) {
    final totals = (json['totals'] as Map?)?.cast<String, dynamic>() ?? const {};
    final lengths = (totals['lengths_ft'] as Map?)?.cast<String, dynamic>() ?? const {};
    final warnings = (json['warnings'] as List?)?.cast<String>() ?? const [];
    final notes = ((json['confidence'] as Map?)?['notes'] as List?)?.cast<String>() ?? const [];
    final source = (json['source'] as Map?)?['method'];
    final rows = <MapEntry<String, String>>[
      if (source != null) MapEntry('source', '$source'),
      for (final e in totals.entries)
        if (e.key != 'lengths_ft') MapEntry(e.key, _fmt(e.value)),
      for (final e in lengths.entries) MapEntry('${e.key} (ft)', _fmt(e.value)),
    ];
    final theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      child: ExpansionTile(
        title: const Text('Model'),
        childrenPadding: const EdgeInsets.all(DemoTokens.pad),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Table(
            defaultColumnWidth: const IntrinsicColumnWidth(),
            children: [
              for (final r in rows)
                TableRow(children: [
                  Padding(
                    padding: const EdgeInsets.only(right: DemoTokens.gapLarge),
                    child: Text(r.key, style: theme.textTheme.bodyMedium),
                  ),
                  Text(r.value, style: theme.textTheme.bodyMedium),
                ]),
            ],
          ),
          const SizedBox(height: DemoTokens.gap),
          Text('Warnings', style: theme.textTheme.titleSmall),
          if (warnings.isEmpty && notes.isEmpty && extraNotes.isEmpty) const Text('None'),
          for (final w in [...warnings, ...notes, ...extraNotes]) Text('- $w'),
        ],
      ),
    );
  }
}
