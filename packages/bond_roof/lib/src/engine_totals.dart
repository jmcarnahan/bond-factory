import 'json_util.dart';

/// The `totals` of a 0.7 envelope (and of `model.totals` when it carries the same keys): one set of figures for the one
/// roof, every one the sum of drawn edges or facets. Every field is nullable: a key the service did not send is "not
/// available", never zero. A key this package does not know is ignored.
class RoofEngineTotals {
  const RoofEngineTotals({
    this.areaSqft,
    this.squares,
    this.roofingPitchedSqft,
    this.roofingFlatSqft,
    this.lowSlopeConfirmSqft,
    this.planesPitchWeighted,
    this.planeCount,
    this.eaveFt,
    this.rakeFt,
    this.flatEdgeFt,
    this.exposedEdgeFt,
    this.eaveRakeFt,
    this.ridgeFt,
    this.hipFt,
    this.valleyFt,
    this.ridgeHipFt,
    this.stepFlashingFt,
    this.wallFlashingFt,
    this.transitionFt,
    this.levelChangeFt,
    this.chimneyCount,
    this.chimneyPerimeterFt,
    this.lanternCount,
    this.lanternSidesFt,
    this.lanternHipsFt,
    this.unitCount,
  });

  /// Null when [j] has none of the keys.
  static RoofEngineTotals? fromJson(Map<String, dynamic> j, [String path = 'totals']) {
    if (!_keys.any((k) => j[k] != null)) return null;
    return RoofEngineTotals(
      areaSqft: numOrNull(j, 'area_sqft', path),
      squares: numOrNull(j, 'squares', path),
      roofingPitchedSqft: numOrNull(j, 'roofing_pitched_sqft', path),
      roofingFlatSqft: numOrNull(j, 'roofing_flat_sqft', path),
      lowSlopeConfirmSqft: numOrNull(j, 'low_slope_confirm_sqft', path),
      planesPitchWeighted: numOrNull(j, 'planes_pitch_weighted', path),
      planeCount: numOrNull(j, 'plane_count', path)?.round(),
      eaveFt: numOrNull(j, 'eave_ft', path),
      rakeFt: numOrNull(j, 'rake_ft', path),
      flatEdgeFt: numOrNull(j, 'flat_edge_ft', path),
      exposedEdgeFt: numOrNull(j, 'exposed_edge_ft', path),
      eaveRakeFt: numOrNull(j, 'eave_rake_ft', path),
      ridgeFt: numOrNull(j, 'ridge_ft', path),
      hipFt: numOrNull(j, 'hip_ft', path),
      valleyFt: numOrNull(j, 'valley_ft', path),
      ridgeHipFt: numOrNull(j, 'ridge_hip_ft', path),
      stepFlashingFt: numOrNull(j, 'step_flashing_ft', path),
      wallFlashingFt: numOrNull(j, 'wall_flashing_ft', path),
      transitionFt: numOrNull(j, 'transition_ft', path),
      levelChangeFt: numOrNull(j, 'level_change_ft', path),
      chimneyCount: numOrNull(j, 'chimney_count', path)?.round(),
      chimneyPerimeterFt: numOrNull(j, 'chimney_perimeter_ft', path),
      lanternCount: numOrNull(j, 'lantern_count', path)?.round(),
      lanternSidesFt: numOrNull(j, 'lantern_sides_ft', path),
      lanternHipsFt: numOrNull(j, 'lantern_hips_ft', path),
      unitCount: numOrNull(j, 'unit_count', path)?.round(),
    );
  }

  static const _keys = [
    'area_sqft', 'squares', 'roofing_pitched_sqft', 'roofing_flat_sqft', 'low_slope_confirm_sqft',
    'planes_pitch_weighted', 'plane_count', 'eave_ft', 'rake_ft', 'flat_edge_ft', 'exposed_edge_ft',
    'eave_rake_ft', 'ridge_ft', 'hip_ft', 'valley_ft', 'ridge_hip_ft', 'step_flashing_ft', 'wall_flashing_ft',
    'transition_ft', 'level_change_ft', 'chimney_count', 'chimney_perimeter_ft', 'lantern_count',
    'lantern_sides_ft', 'lantern_hips_ft', 'unit_count',
  ];

  /// Key by key: every value of [primary], and of [fallback] where [primary] has none. Null when both are.
  static RoofEngineTotals? merge(RoofEngineTotals? primary, RoofEngineTotals? fallback) =>
      fromJson({...?fallback?.toJson(), ...?primary?.toJson()});

  /// The wire keys this class reads (a test helper asserts an envelope uses no other).
  static const List<String> knownKeys = _keys;

  /// Sloped area of all facets, square feet.
  final double? areaSqft;
  /// `areaSqft / 100`.
  final double? squares;
  /// Pitched and low-slope ("flat") roofing area, split at 2/12.
  final double? roofingPitchedSqft;
  final double? roofingFlatSqft;
  /// Area of the borderline ("low slope, confirm") facets.
  final double? lowSlopeConfirmSqft;
  /// Area-weighted fitted pitch (rise per 12) of the pitched facets.
  final double? planesPitchWeighted;
  /// Number of facets.
  final int? planeCount;
  /// Outer roof edge by type.
  final double? eaveFt;
  final double? rakeFt;
  final double? flatEdgeFt;
  /// The free edge of an upper roof at every step, plus the sides of a lantern.
  final double? exposedEdgeFt;
  /// `eave + rake + flat edge + exposed edge`.
  final double? eaveRakeFt;
  /// Inner lines.
  final double? ridgeFt;
  final double? hipFt;
  final double? valleyFt;
  /// `ridge + hip`.
  final double? ridgeHipFt;
  /// Sidewall flashing: a step that runs down the lower slope.
  final double? stepFlashingFt;
  /// Headwall flashing: a step across the lower slope, or onto a low-slope section.
  final double? wallFlashingFt;
  /// Pitched meets low-slope with no height step.
  final double? transitionFt;
  /// A step between two low-slope sections.
  final double? levelChangeFt;
  /// From `model.objects`.
  final int? chimneyCount;
  final double? chimneyPerimeterFt;
  final int? lanternCount;
  /// The perimeter of every lantern: the part of [exposedEdgeFt] that is lantern sides.
  final double? lanternSidesFt;
  /// An estimate of the lanterns' own hips; in no ridge + hip.
  final double? lanternHipsFt;
  /// Objects of kind unit: a box on a flat or low-slope facet.
  final int? unitCount;

  Map<String, dynamic> toJson() => {
        if (areaSqft != null) 'area_sqft': areaSqft,
        if (squares != null) 'squares': squares,
        if (roofingPitchedSqft != null) 'roofing_pitched_sqft': roofingPitchedSqft,
        if (roofingFlatSqft != null) 'roofing_flat_sqft': roofingFlatSqft,
        if (lowSlopeConfirmSqft != null) 'low_slope_confirm_sqft': lowSlopeConfirmSqft,
        if (planesPitchWeighted != null) 'planes_pitch_weighted': planesPitchWeighted,
        if (planeCount != null) 'plane_count': planeCount,
        if (eaveFt != null) 'eave_ft': eaveFt,
        if (rakeFt != null) 'rake_ft': rakeFt,
        if (flatEdgeFt != null) 'flat_edge_ft': flatEdgeFt,
        if (exposedEdgeFt != null) 'exposed_edge_ft': exposedEdgeFt,
        if (eaveRakeFt != null) 'eave_rake_ft': eaveRakeFt,
        if (ridgeFt != null) 'ridge_ft': ridgeFt,
        if (hipFt != null) 'hip_ft': hipFt,
        if (valleyFt != null) 'valley_ft': valleyFt,
        if (ridgeHipFt != null) 'ridge_hip_ft': ridgeHipFt,
        if (stepFlashingFt != null) 'step_flashing_ft': stepFlashingFt,
        if (wallFlashingFt != null) 'wall_flashing_ft': wallFlashingFt,
        if (transitionFt != null) 'transition_ft': transitionFt,
        if (levelChangeFt != null) 'level_change_ft': levelChangeFt,
        if (chimneyCount != null) 'chimney_count': chimneyCount,
        if (chimneyPerimeterFt != null) 'chimney_perimeter_ft': chimneyPerimeterFt,
        if (lanternCount != null) 'lantern_count': lanternCount,
        if (lanternSidesFt != null) 'lantern_sides_ft': lanternSidesFt,
        if (lanternHipsFt != null) 'lantern_hips_ft': lanternHipsFt,
        if (unitCount != null) 'unit_count': unitCount,
      };

  @override
  bool operator ==(Object other) => other is RoofEngineTotals && _same(other.toJson(), toJson());

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
