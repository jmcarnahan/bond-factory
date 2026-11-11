import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

void main() {
  test('variants are sums of the length totals', () {
    final t = RoofTotals(
      totalAreaSqft: 0,
      pitchedAreaSqft: 0,
      flatAreaSqft: 0,
      predominantPitchRise: 0,
      predominantPitchAreaSqft: 0,
      squares: 0,
      lengthsFt: {
        for (final e in EdgeType.values) e: 0.0,
        EdgeType.eave: 100,
        EdgeType.rake: 20,
        EdgeType.ridge: 30,
        EdgeType.hip: 12.5,
      },
    );
    final v = RoofTotalsVariants.of(t);
    expect(v.dripEdgeEaveFt, 100);
    expect(v.dripEdgeEaveRakeFt, 120);
    expect(v.ridgeCapRidgeFt, 30);
    expect(v.ridgeCapRidgeHipFt, 42.5);
  });

  for (final e in loadEnvelopes()) {
    test('${e.name}: computed variants equal the envelope keys within 0.05 ft', () {
      final v = RoofTotalsVariants.of(e.measurement.model.totals);
      final t = e.json['totals'] as Map<String, dynamic>;
      expect(v.dripEdgeEaveFt, closeTo((t['drip_edge_eave_ft'] as num).toDouble(), 0.05));
      expect(v.dripEdgeEaveRakeFt, closeTo((t['drip_edge_eave_rake_ft'] as num).toDouble(), 0.05));
      expect(v.ridgeCapRidgeFt, closeTo((t['ridge_cap_ridge_ft'] as num).toDouble(), 0.05));
      expect(v.ridgeCapRidgeHipFt, closeTo((t['ridge_cap_ridge_hip_ft'] as num).toDouble(), 0.05));
      expect(e.measurement.totals.variants.dripEdgeEaveRakeFt, closeTo(v.dripEdgeEaveRakeFt, 0.05));
    });

    test('${e.name}: the other envelope totals match the model within 0.05 ft', () {
      final m = e.measurement;
      final l = m.model.totals.lengthsFt;
      expect(m.totals.eaveFt, closeTo(l[EdgeType.eave]!, 0.05));
      expect(m.totals.rakeFt, closeTo(l[EdgeType.rake]!, 0.05));
      expect(m.totals.ridgeFt, closeTo(l[EdgeType.ridge]!, 0.05));
      expect(m.totals.hipFt, closeTo(l[EdgeType.hip]!, 0.05));
      expect(m.totals.valleyFt, closeTo(l[EdgeType.valley]!, 0.05));
      expect(m.totals.stepFlashingFt, closeTo(l[EdgeType.stepFlashing]!, 0.05));
      expect(m.totals.areaSqft, closeTo(m.model.totals.totalAreaSqft, 0.5));
    });
  }

  test('every model fixture yields non-negative variants with eave+rake >= eave', () {
    for (final f in loadFixtures()) {
      final v = RoofTotalsVariants.of(RoofModel.fromJson(f.json).totals);
      expect(v.dripEdgeEaveRakeFt, greaterThanOrEqualTo(v.dripEdgeEaveFt), reason: f.name);
      expect(v.ridgeCapRidgeHipFt, greaterThanOrEqualTo(v.ridgeCapRidgeFt), reason: f.name);
    }
  });
}
