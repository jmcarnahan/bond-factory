import 'json_util.dart';

/// `totals.complexity` of envelope 0.4: how cut-up the roof is.
class RoofComplexity {
  const RoofComplexity({this.facets, this.hipValleyFtPerSquare, this.hint});

  factory RoofComplexity.fromJson(Map<String, dynamic> j, [String path = 'totals.complexity']) => RoofComplexity(
        facets: numOrNull(j, 'facets', path)?.round(),
        hipValleyFtPerSquare: numOrNull(j, 'hip_valley_ft_per_square', path),
        hint: j['hint'] is String ? j['hint'] as String : null,
      );

  final int? facets;
  final double? hipValleyFtPerSquare;

  /// `simple` or `cut_up` (a value this package does not know is kept as is).
  final String? hint;

  Map<String, dynamic> toJson() => {
        if (facets != null) 'facets': facets,
        if (hipValleyFtPerSquare != null) 'hip_valley_ft_per_square': hipValleyFtPerSquare,
        if (hint != null) 'hint': hint,
      };

  @override
  bool operator ==(Object other) =>
      other is RoofComplexity &&
      other.facets == facets &&
      other.hipValleyFtPerSquare == hipValleyFtPerSquare &&
      other.hint == hint;

  @override
  int get hashCode => Object.hash(facets, hipValleyFtPerSquare, hint);
}

/// The totals keys envelope 0.4 adds (and the cost-sheet keys 0.3 added), all nullable: a missing
/// key means "not available", never zero. Read from the envelope `totals` and from `model.totals`.
class RoofEngineTotals {
  const RoofEngineTotals({
    this.roofingPitchedSqft,
    this.roofingFlatSqft,
    this.roofingPitchedSquares,
    this.roofingFlatSquares,
    this.lowSlopeConfirmSqft,
    this.areaSqftWallLine,
    this.areaSqftRoofEdge,
    this.outlinePerimeterWallFt,
    this.overhangFtMedian,
    this.flatEdgeFt,
    this.levelChangeFt,
    this.complexity,
    this.planesSurfaceAreaSqft,
    this.planesPitchWeighted,
    this.outlinePerimeterFt,
  });

  /// Null when [j] has none of the keys.
  static RoofEngineTotals? fromJson(Map<String, dynamic> j, [String path = 'totals']) {
    if (!_keys.any((k) => j[k] != null)) return null;
    double? n(String key) => numOrNull(j, key, path);
    return RoofEngineTotals(
      roofingPitchedSqft: n('roofing_pitched_sqft'),
      roofingFlatSqft: n('roofing_flat_sqft'),
      roofingPitchedSquares: n('roofing_pitched_squares'),
      roofingFlatSquares: n('roofing_flat_squares'),
      lowSlopeConfirmSqft: n('low_slope_confirm_sqft'),
      areaSqftWallLine: n('area_sqft_wall_line'),
      areaSqftRoofEdge: n('area_sqft_roof_edge'),
      outlinePerimeterWallFt: n('outline_perimeter_wall_ft'),
      overhangFtMedian: n('overhang_ft_median'),
      flatEdgeFt: n('flat_edge_ft'),
      levelChangeFt: n('level_change_ft'),
      complexity: j['complexity'] == null
          ? null
          : RoofComplexity.fromJson(asMap(j['complexity'], '$path.complexity'), '$path.complexity'),
      planesSurfaceAreaSqft: n('planes_surface_area_sqft'),
      planesPitchWeighted: n('planes_pitch_weighted'),
      outlinePerimeterFt: n('outline_perimeter_ft'),
    );
  }

  static const _keys = [
    'roofing_pitched_sqft', 'roofing_flat_sqft', 'roofing_pitched_squares', 'roofing_flat_squares',
    'low_slope_confirm_sqft', 'area_sqft_wall_line', 'area_sqft_roof_edge', 'outline_perimeter_wall_ft',
    'overhang_ft_median', 'flat_edge_ft', 'level_change_ft', 'complexity', 'planes_surface_area_sqft',
    'planes_pitch_weighted', 'outline_perimeter_ft',
  ];

  /// Pitched and flat roofing (split at 2.0/12), square feet and squares.
  final double? roofingPitchedSqft, roofingFlatSqft, roofingPitchedSquares, roofingFlatSquares;

  /// Area of the borderline ("low slope, confirm") facets.
  final double? lowSlopeConfirmSqft;

  /// Area to the wall line, and the area AS DRAWN to the roof edge. Neither is the priced area: that is
  /// [planesSurfaceAreaSqft] (priced, equals pitched + flat roofing).
  final double? areaSqftWallLine, areaSqftRoofEdge;

  /// Outline perimeter at the wall line (`outlinePerimeterFt` is the roof-edge one).
  final double? outlinePerimeterWallFt;
  final double? overhangFtMedian, flatEdgeFt, levelChangeFt;
  final RoofComplexity? complexity;

  /// The cost-sheet keys: the PRICED surface area (pitched + flat roofing), area-weighted pitch of pitched
  /// facets, roof-edge perimeter.
  final double? planesSurfaceAreaSqft, planesPitchWeighted, outlinePerimeterFt;

  /// True when the pitched and flat squares are both known (the totals table then lists them
  /// on separate rows).
  bool get hasRoofing => roofingPitchedSquares != null || roofingFlatSquares != null;

  Map<String, dynamic> toJson() => {
        if (roofingPitchedSqft != null) 'roofing_pitched_sqft': roofingPitchedSqft,
        if (roofingFlatSqft != null) 'roofing_flat_sqft': roofingFlatSqft,
        if (roofingPitchedSquares != null) 'roofing_pitched_squares': roofingPitchedSquares,
        if (roofingFlatSquares != null) 'roofing_flat_squares': roofingFlatSquares,
        if (lowSlopeConfirmSqft != null) 'low_slope_confirm_sqft': lowSlopeConfirmSqft,
        if (areaSqftWallLine != null) 'area_sqft_wall_line': areaSqftWallLine,
        if (areaSqftRoofEdge != null) 'area_sqft_roof_edge': areaSqftRoofEdge,
        if (outlinePerimeterWallFt != null) 'outline_perimeter_wall_ft': outlinePerimeterWallFt,
        if (overhangFtMedian != null) 'overhang_ft_median': overhangFtMedian,
        if (flatEdgeFt != null) 'flat_edge_ft': flatEdgeFt,
        if (levelChangeFt != null) 'level_change_ft': levelChangeFt,
        if (complexity != null) 'complexity': complexity!.toJson(),
        if (planesSurfaceAreaSqft != null) 'planes_surface_area_sqft': planesSurfaceAreaSqft,
        if (planesPitchWeighted != null) 'planes_pitch_weighted': planesPitchWeighted,
        if (outlinePerimeterFt != null) 'outline_perimeter_ft': outlinePerimeterFt,
      };

  @override
  bool operator ==(Object other) =>
      other is RoofEngineTotals && _same(other.toJson(), toJson());

  @override
  int get hashCode => Object.hashAll([for (final e in toJson().entries) Object.hash(e.key, '${e.value}')]);

  static bool _same(Map<String, dynamic> a, Map<String, dynamic> b) {
    if (a.length != b.length) return false;
    for (final e in a.entries) {
      if ('${b[e.key]}' != '${e.value}') return false;
    }
    return true;
  }
}
