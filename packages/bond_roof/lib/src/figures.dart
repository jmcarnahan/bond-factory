import 'dart:math' as math;

import 'format.dart';
import 'labels.dart';
import 'model.dart';

/// The figures of one roof, read in ONE place for the legend, the area header, the summary and the totals table.
///
/// A figure comes from the 0.6 totals key when the model carries it, else from the model's own facets and edges. A key
/// the service did not send is never read as zero: where there is nothing to sum from, the figure is null or absent.
class RoofFigures {
  const RoofFigures._({
    required this.areaSqft,
    required this.squares,
    required this.pitchedSqft,
    required this.flatSqft,
    required this.lowSlopeConfirmSqft,
    required this.pitch,
    required this.facets,
    required this.lengths,
    required this.exposedEdgeFt,
    required this.eaveRakeFt,
    required this.ridgeHipFt,
    required this.chimneys,
    required this.lanterns,
  });

  /// [envelope] is the envelope's own `totals`: read key by key, wherever the model's own totals lack the key.
  factory RoofFigures.of(RoofModel m, {RoofEngineTotals? envelope}) {
    final e = RoofEngineTotals.merge(m.totals.engine, envelope);
    double len(EdgeType t, double? key) => key ?? m.totals.lengthsFt[t] ?? 0.0;
    final lengths = <EdgeType, double>{
      EdgeType.eave: len(EdgeType.eave, e?.eaveFt),
      EdgeType.rake: len(EdgeType.rake, e?.rakeFt),
      EdgeType.flatEdge: len(EdgeType.flatEdge, e?.flatEdgeFt),
      EdgeType.ridge: len(EdgeType.ridge, e?.ridgeFt),
      EdgeType.hip: len(EdgeType.hip, e?.hipFt),
      EdgeType.valley: len(EdgeType.valley, e?.valleyFt),
      EdgeType.stepFlashing: len(EdgeType.stepFlashing, e?.stepFlashingFt),
      EdgeType.wallFlashing: len(EdgeType.wallFlashing, e?.wallFlashingFt),
      EdgeType.transition: len(EdgeType.transition, e?.transitionFt),
      EdgeType.levelChange: len(EdgeType.levelChange, e?.levelChangeFt),
      EdgeType.unspecified: len(EdgeType.unspecified, null),
    };
    // The upper roof's free edge at each step (sidewall + headwall) plus the perimeter of every lantern.
    final exposed = e?.exposedEdgeFt ??
        lengths[EdgeType.stepFlashing]! +
            lengths[EdgeType.wallFlashing]! +
            m.objects.where((o) => o.kind == ObjectKind.lantern).fold(0.0, (a, o) => a + o.perimeterFt);
    final eaveRake = e?.eaveRakeFt ??
        lengths[EdgeType.eave]! + lengths[EdgeType.rake]! + lengths[EdgeType.flatEdge]! + exposed;
    // "Ridge + hip" can never be smaller than "ridge".
    final ridgeHip =
        math.max(e?.ridgeHipFt ?? lengths[EdgeType.ridge]! + lengths[EdgeType.hip]!, lengths[EdgeType.ridge]!);
    final area = e?.areaSqft ?? m.totals.totalAreaSqft;
    int count(ObjectKind k, int? key) => key ?? m.objects.where((o) => o.kind == k).length;
    return RoofFigures._(
      areaSqft: area,
      squares: e?.squares ?? area / 100,
      pitchedSqft: e?.roofingPitchedSqft ?? m.pitchedAreaSqftByRoofType,
      flatSqft: e?.roofingFlatSqft ?? m.flatAreaSqftByRoofType,
      lowSlopeConfirmSqft: e?.lowSlopeConfirmSqft ?? 0.0,
      pitch: e?.planesPitchWeighted ?? _weightedPitch(m),
      facets: e?.planeCount ?? m.facets.length,
      lengths: lengths,
      exposedEdgeFt: exposed,
      eaveRakeFt: eaveRake,
      ridgeHipFt: ridgeHip,
      chimneys: count(ObjectKind.chimney, e?.chimneyCount),
      lanterns: count(ObjectKind.lantern, e?.lanternCount),
    );
  }

  /// Area-weighted pitch of the pitched facets, or null when the roof has none.
  static double? _weightedPitch(RoofModel m) {
    var weight = 0.0, sum = 0.0;
    for (final f in m.facets) {
      if (f.kind == FacetKind.flat || f.isFlatRoofType) continue;
      weight += f.areaSqft;
      sum += f.areaSqft * f.pitchRise;
    }
    return weight > 0 ? sum / weight : null;
  }

  final double areaSqft, squares, pitchedSqft, flatSqft, lowSlopeConfirmSqft;

  /// Area-weighted fitted pitch (rise per 12) of the pitched facets; null when the roof has no pitched facet.
  final double? pitch;
  final int facets;

  /// Feet per edge type (the types of [EdgeType] except a flat seam); zero when the roof has none.
  final Map<EdgeType, double> lengths;
  final double exposedEdgeFt, eaveRakeFt, ridgeHipFt;
  final int chimneys, lanterns;

  /// True when the roof has both pitched and flat roofing (only then are the two split on their own rows).
  bool get hasBothKinds => pitchedSqft > 0 && flatSqft > 0;
}

/// One line of the totals: a stable [id], the label and the value as text.
class TotalRow {
  const TotalRow(this.id, this.label, this.value);
  final String id, label, value;
}

/// The totals rows, in report order. A row exists only when the roof has the thing: a gable roof has no hip row, a roof
/// without a step has no flashing row. The summary block and the totals table both print this list; [envelope] is the
/// envelope's `totals`, read when the model's own totals carry no 0.6 keys.
List<TotalRow> totalRows(RoofModel m, RoofLabels l, {RoofEngineTotals? envelope}) {
  final f = RoofFigures.of(m, envelope: envelope);
  String ft(double v) => feetInches(v, labels: l);
  String area(double v) => '${sqft(v)} ${l.unitSqft}';
  final pitch = f.pitch;
  final rows = <TotalRow>[
    TotalRow('area', l.totalArea, '${area(f.areaSqft)}  (${f.squares.toStringAsFixed(2)} ${l.unitSquares})'),
    if (f.hasBothKinds) TotalRow('pitched', l.totalsRoofingPitched, area(f.pitchedSqft)),
    if (f.hasBothKinds) TotalRow('flat', l.totalsRoofingFlat, area(f.flatSqft)),
    if (f.lowSlopeConfirmSqft > 0) TotalRow('low_slope', l.totalsLowSlopeConfirm, area(f.lowSlopeConfirmSqft)),
    if (pitch != null) TotalRow('pitch', l.pitch, pitchLabel(pitch, labels: l)),
  ];
  void length(String id, String label, double v) {
    if (v > 0) rows.add(TotalRow(id, label, ft(v)));
  }

  length('eave', l.legendEave, f.lengths[EdgeType.eave]!);
  length('rake', l.legendRake, f.lengths[EdgeType.rake]!);
  length('flat_edge', l.legendFlatEdge, f.lengths[EdgeType.flatEdge]!);
  length('exposed_edge', l.totalsExposedEdge, f.exposedEdgeFt);
  // Follows the contract's definition (the outer roof edge plus the exposed edges inside the roof), which is wider than its label.
  length('eave_rake', l.totalsEaveRake, f.eaveRakeFt);
  length('ridge', l.legendRidge, f.lengths[EdgeType.ridge]!);
  length('hip', l.legendHip, f.lengths[EdgeType.hip]!);
  length('ridge_hip', l.totalsRidgeHip, f.ridgeHipFt);
  length('valley', l.legendValley, f.lengths[EdgeType.valley]!);
  length('step_flashing', l.totalsSidewall, f.lengths[EdgeType.stepFlashing]!);
  length('wall_flashing', l.totalsHeadwall, f.lengths[EdgeType.wallFlashing]!);
  length('transition', l.totalsTransition, f.lengths[EdgeType.transition]!);
  length('level_change', l.legendLevelChange, f.lengths[EdgeType.levelChange]!);
  length('unspecified', l.legendUnspecified, f.lengths[EdgeType.unspecified]!);
  if (f.chimneys > 0) rows.add(TotalRow('chimneys', l.totalsChimneys, '${f.chimneys}'));
  if (f.lanterns > 0) rows.add(TotalRow('lanterns', l.totalsLanterns, '${f.lanterns}'));
  rows.add(TotalRow('facets', l.facets, '${f.facets}'));
  return rows;
}
