import 'labels_defaults.dart';
import 'model_parts.dart' show EdgeType;

/// Every user-visible string the diagrams, the PDF and the report widgets print.
///
/// Strings enter the shared widgets through this object (see docs/decisions/
/// 2026-11-08-shared-modules-policy.md). English is the default; an app supplies other
/// languages with [RoofLabels.fromMap], keyed by [keys]. Keys it leaves out keep the English
/// text. Template strings carry `{name}` placeholders that [fill] replaces.
///
/// Service text (confidence notes, warnings, verifier notes) is not translated here.
class RoofLabels {
  /// The English labels.
  const RoofLabels() : _m = roofLabelDefaults;

  const RoofLabels._(this._m);

  /// Builds labels from a map keyed by [keys]. Unknown keys are ignored; missing, null, empty and
  /// whitespace-only values keep the English default.
  factory RoofLabels.fromMap(Map<String, String?> overrides) => RoofLabels._(Map.unmodifiable({
        for (final e in roofLabelDefaults.entries)
          e.key: switch (overrides[e.key]) {
            final String v when v.trim().isNotEmpty => v,
            _ => e.value,
          },
      }));

  /// The wire keys, in a stable order. Every key is a snake_case name.
  static final List<String> keys = List.unmodifiable(roofLabelDefaults.keys);

  /// Replaces each `{name}` in [template] with `values[name]`; unknown names are left as is.
  static String fill(String template, Map<String, String> values) =>
      template.replaceAllMapped(RegExp(r'\{([a-z_]+)\}'), (m) => values[m[1]] ?? m[0]!);

  final Map<String, String> _m;

  /// Every key with its current text.
  Map<String, String> toMap() => Map.of(_m);

  /// A copy with [overrides] applied (unknown keys ignored).
  RoofLabels copyWith(Map<String, String?> overrides) => RoofLabels.fromMap({..._m, ...overrides});

  /// The text for [key]; throws [ArgumentError] for a key that is not in [keys].
  String operator [](String key) =>
      _m[key] ?? (throw ArgumentError.value(key, 'key', 'not a RoofLabels key'));

  /// The legend name of an edge type.
  String edgeName(EdgeType t) => switch (t) {
        EdgeType.eave => legendEave,
        EdgeType.rake => legendRake,
        EdgeType.ridge => legendRidge,
        EdgeType.hip => legendHip,
        EdgeType.valley => legendValley,
        EdgeType.stepFlashing => legendStepFlashing,
        EdgeType.wallFlashing => legendWallFlashing,
        EdgeType.parapet => legendParapet,
        EdgeType.transition => legendTransition,
        EdgeType.unspecified => legendUnspecified,
      };

  @override
  bool operator ==(Object other) {
    if (other is! RoofLabels) return false;
    if (identical(_m, other._m)) return true;
    for (final e in _m.entries) {
      if (other._m[e.key] != e.value) return false;
    }
    return true;
  }

  @override
  int get hashCode => Object.hashAll(_m.values);

  String get legendEave => _m['legend_eave']!;
  String get legendRake => _m['legend_rake']!;
  String get legendRidge => _m['legend_ridge']!;
  String get legendHip => _m['legend_hip']!;
  String get legendValley => _m['legend_valley']!;
  String get legendStepFlashing => _m['legend_step_flashing']!;
  String get legendWallFlashing => _m['legend_wall_flashing']!;
  String get legendParapet => _m['legend_parapet']!;
  String get legendTransition => _m['legend_transition']!;
  String get legendUnspecified => _m['legend_unspecified']!;
  String get lengthTitle => _m['length_title']!;
  String get lengthCaption => _m['length_caption']!;
  String get areaTitle => _m['area_title']!;
  String get areaCaption => _m['area_caption']!;
  String get summaryCaption => _m['summary_caption']!;
  String get summaryPageTitle => _m['summary_page_title']!;
  String get addressMissing => _m['address_missing']!;
  String get totalArea => _m['total_area']!;
  String get squares => _m['squares']!;
  String get pitchedArea => _m['pitched_area']!;
  String get flatArea => _m['flat_area']!;
  String get predominantPitch => _m['predominant_pitch']!;
  String get facets => _m['facets']!;
  String get edgeTotal => _m['edge_total']!;
  String get confidence => _m['confidence']!;
  String get totalPitchedArea => _m['total_pitched_area']!;
  String get totalFlatArea => _m['total_flat_area']!;
  String get predominantPitchArea => _m['predominant_pitch_area']!;
  String get twoStoryArea => _m['two_story_area']!;
  String get twoLayerArea => _m['two_layer_area']!;
  String get unspecifiedPitchArea => _m['unspecified_pitch_area']!;
  String get notAvailable => _m['not_available']!;
  String get pitchFlat => _m['pitch_flat']!;
  String get unitFt => _m['unit_ft']!;
  String get unitIn => _m['unit_in']!;
  String get unitSqft => _m['unit_sqft']!;
  String get unitSquares => _m['unit_squares']!;
  String get sourceHeading => _m['source_heading']!;
  String get sourceMethod => _m['source_method']!;
  String get sourceFootprint => _m['source_footprint']!;
  String get footprintId => _m['footprint_id']!;
  String get footprintArea => _m['footprint_area']!;
  String get sourceLidar => _m['source_lidar']!;
  String get lidarPoints => _m['lidar_points']!;
  String get sourceSolar => _m['source_solar']!;
  String get solarSegments => _m['solar_segments']!;
  String get modelGenerated => _m['model_generated']!;
  String get unknown => _m['unknown']!;
  String get methodLidarSkeleton => _m['method_lidar_skeleton']!;
  String get methodLidarAgent => _m['method_lidar_agent']!;
  String get methodSolarAgent => _m['method_solar_agent']!;
  String get methodManual => _m['method_manual']!;
  String get methodFixture => _m['method_fixture']!;
  String get confidenceNotesHeading => _m['confidence_notes_heading']!;
  String get warnings => _m['warnings']!;
  String get excludedOpeningsHeading => _m['excluded_openings_heading']!;
  String get excludedFromAreas => _m['excluded_from_areas']!;
  String get footerLength => _m['footer_length']!;
  String get footerArea => _m['footer_area']!;
  String get compassNorth => _m['compass_north']!;
  String get pdfTitle => _m['pdf_title']!;
  String get actionPrint => _m['action_print']!;
  String get actionSavePdf => _m['action_save_pdf']!;
  String get actionSharePdf => _m['action_share_pdf']!;
  String get statusPreparingPrint => _m['status_preparing_print']!;
  String get statusPrinted => _m['status_printed']!;
  String get statusBuildingPdf => _m['status_building_pdf']!;
  String get statusSaved => _m['status_saved']!;
  String get statusSharingPdf => _m['status_sharing_pdf']!;
  String get statusShared => _m['status_shared']!;
  String get statusFailed => _m['status_failed']!;
  String get totalsHeading => _m['totals_heading']!;
  String get variantDripEdgeEave => _m['variant_drip_edge_eave']!;
  String get variantDripEdgeEaveRake => _m['variant_drip_edge_eave_rake']!;
  String get variantRidgeCapRidge => _m['variant_ridge_cap_ridge']!;
  String get variantRidgeCapRidgeHip => _m['variant_ridge_cap_ridge_hip']!;
  String get verification => _m['verification']!;
  String get verdictPass => _m['verdict_pass']!;
  String get verdictAdjusted => _m['verdict_adjusted']!;
  String get verdictFail => _m['verdict_fail']!;
  String get verdictUnverified => _m['verdict_unverified']!;
  String get generated => _m['generated']!;}
