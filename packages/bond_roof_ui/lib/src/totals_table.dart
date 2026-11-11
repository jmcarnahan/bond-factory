import 'package:flutter/material.dart';
import 'package:bond_roof/bond_roof.dart';

import 'tokens.dart';

/// The measurement as inline text rows: area, pitch, facets, each edge total, the two paired
/// variants (drip edge: eave / eave + rake; ridge cap: ridge / ridge + hip), confidence, the
/// verification verdict with its first note, and when it was generated. No popups.
class RoofTotalsTable extends StatelessWidget {
  const RoofTotalsTable(this.measurement, {super.key, this.labels = const RoofLabels()});

  final RoofMeasurement measurement;
  final RoofLabels labels;

  /// The verdict as text from [labels]; an unknown verdict reads as not verified.
  static String verdictLabel(RoofVerdict v, RoofLabels l) => switch (v) {
        RoofVerdict.pass => l.verdictPass,
        RoofVerdict.adjusted => l.verdictAdjusted,
        RoofVerdict.fail => l.verdictFail,
        RoofVerdict.unverified || RoofVerdict.unknown => l.verdictUnverified,
      };

  static String _generated(DateTime t) {
    final u = t.toUtc();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${u.year}-${two(u.month)}-${two(u.day)} ${two(u.hour)}:${two(u.minute)} UTC';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final t = measurement.totals;
    String ft(double v) => feetInches(v, labels: labels);
    final rows = <(String, String)>[
      (labels.totalArea, '${sqft(t.areaSqft)} ${labels.unitSqft}  (${t.squares.toStringAsFixed(2)} ${labels.unitSquares})'),
      (labels.predominantPitch, pitchLabel(t.predominantPitch, labels: labels)),
      (labels.facets, '${t.facets}'),
      (labels.legendEave, ft(t.eaveFt)),
      (labels.legendRake, ft(t.rakeFt)),
      (labels.legendRidge, ft(t.ridgeFt)),
      (labels.legendHip, ft(t.hipFt)),
      (labels.legendValley, ft(t.valleyFt)),
      (labels.legendStepFlashing, ft(t.stepFlashingFt)),
      (labels.variantDripEdgeEave, ft(t.dripEdgeEaveFt)),
      (labels.variantDripEdgeEaveRake, ft(t.dripEdgeEaveRakeFt)),
      (labels.variantRidgeCapRidge, ft(t.ridgeCapRidgeFt)),
      (labels.variantRidgeCapRidgeHip, ft(t.ridgeCapRidgeHipFt)),
      (labels.confidence, '${(measurement.confidenceScore * 100).round()}%'),
    ];
    final v = measurement.verification;
    final verdict = verdictLabel(v.verdict, labels);
    final verification = v.notes.isEmpty ? verdict : '$verdict - ${v.notes.first}';
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
          _Row(labels.verification, verification, bold: false),
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
