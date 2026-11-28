import 'package:flutter/material.dart';
import 'package:bond_roof/bond_roof.dart';

import 'tokens.dart';

/// The measurement as inline text rows: the totals the roof has (area, pitch, each length, the chimney, lantern and unit counts: see
/// [totalRows]), confidence, and when it was generated. A roof never gets a row for a thing it does not have. No popups.
class RoofTotalsTable extends StatelessWidget {
  const RoofTotalsTable(this.measurement, {super.key, this.labels = const RoofLabels()});

  final RoofMeasurement measurement;
  final RoofLabels labels;

  static String _generated(DateTime t) {
    final u = t.toUtc();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${u.year}-${two(u.month)}-${two(u.day)} ${two(u.hour)}:${two(u.minute)} UTC';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rows = [
      for (final r in totalRows(measurement.model, labels, envelope: measurement.totals)) (r.label, r.value),
      (labels.confidence, '${(measurement.confidenceScore * 100).round()}%'),
    ];
    final generated = measurement.generatedAt;
    return Semantics(
      container: true,
      label: labels.totalsHeading,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(labels.totalsHeading, style: theme.textTheme.titleMedium),
          const SizedBox(height: RoofUiTokens.gap / 2),
          for (final (label, value) in rows) _Row(label, value),
          const SizedBox(height: RoofUiTokens.gap / 2),
          if (generated != null) _Row(labels.generated, _generated(generated), bold: false),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value, {this.bold = true});

  final String label, value;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 2, child: Text(label, style: theme.textTheme.bodyMedium)),
          const SizedBox(width: RoofUiTokens.gap),
          Expanded(
            flex: 3,
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: theme.textTheme.bodyMedium?.copyWith(fontWeight: bold ? FontWeight.w700 : FontWeight.w400),
            ),
          ),
        ],
      ),
    );
  }
}
