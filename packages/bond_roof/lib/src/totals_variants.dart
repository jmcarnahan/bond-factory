import 'model_parts.dart';
import 'totals.dart';

/// The two paired totals roofers quote both ways: drip edge covers the eaves, or the eaves and
/// the rakes; ridge cap covers the ridges, or the ridges and the hips. Computed from the ten
/// `lengths_ft` values, so it works for a 0.1 model as well as a 0.2 envelope.
class RoofTotalsVariants {
  const RoofTotalsVariants({
    required this.dripEdgeEaveFt,
    required this.dripEdgeEaveRakeFt,
    required this.ridgeCapRidgeFt,
    required this.ridgeCapRidgeHipFt,
  });

  factory RoofTotalsVariants.of(RoofTotals t) {
    double len(EdgeType e) => t.lengthsFt[e] ?? 0.0;
    return RoofTotalsVariants(
      dripEdgeEaveFt: len(EdgeType.eave),
      dripEdgeEaveRakeFt: len(EdgeType.eave) + len(EdgeType.rake),
      ridgeCapRidgeFt: len(EdgeType.ridge),
      ridgeCapRidgeHipFt: len(EdgeType.ridge) + len(EdgeType.hip),
    );
  }

  final double dripEdgeEaveFt, dripEdgeEaveRakeFt, ridgeCapRidgeFt, ridgeCapRidgeHipFt;
}
