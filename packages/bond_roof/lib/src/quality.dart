import 'json_util.dart';

/// `model.quality` of envelope 0.4 (named `RoofEngineQuality` because apps often have their own `RoofQuality`). Every field is nullable ("not available"); the whole block
/// stays in [raw] so keys this package does not model survive.
class RoofEngineQuality {
  const RoofEngineQuality({
    this.engine,
    this.fitAll,
    this.fitCovered,
    this.coverage,
    this.supportedPct,
    this.densityPtsM2,
    this.flatShare,
    this.parcelMatch,
    this.outlineSource,
    this.verdict,
    this.raw = const {},
  });

  factory RoofEngineQuality.fromJson(Map<String, dynamic> j, [String path = 'quality']) {
    String? s(String key) => j[key] is String ? j[key] as String : null;
    return RoofEngineQuality(
      engine: s('engine'),
      fitAll: numOrNull(j, 'fit_all', path),
      fitCovered: numOrNull(j, 'fit_covered', path),
      coverage: numOrNull(j, 'coverage', path),
      supportedPct: numOrNull(j, 'supported_pct', path),
      densityPtsM2: numOrNull(j, 'density_pts_m2', path),
      flatShare: numOrNull(j, 'flat_share', path),
      parcelMatch: s('parcel_match'),
      outlineSource: s('outline_source'),
      verdict: s('verdict'),
      raw: Map.of(j),
    );
  }

  /// `planes/1` for the plane engine.
  final String? engine;

  /// Share of ALL reference roof points the facets explain, and of the covered ones; 0..1.
  final double? fitAll, fitCovered;

  /// Share of the reference outline the facets cover; 0..1.
  final double? coverage;

  /// Planar support, percent.
  final double? supportedPct;

  /// Roof points per square metre.
  final double? densityPtsM2;

  /// Flat priced area over total priced area, 0..1 (roof_measure 0.5.1; null on older rows).
  final double? flatShare;

  /// `exact`, `street`, `nearest` or `given`.
  final String? parcelMatch;
  final String? outlineSource;

  /// `ok`, `low_density`, `outline_mismatch`, `poor_fit` or `not_exact_parcel` (others are kept as is).
  final String? verdict;

  /// The whole `quality` object.
  final Map<String, dynamic> raw;

  Map<String, dynamic> toJson() => Map.of(raw);
}

/// `model.source.building` of envelope 0.4: which building was measured.
class RoofBuilding {
  const RoofBuilding({this.parcelId, this.outlineId, this.outlineCentroid, this.chosenBy});

  factory RoofBuilding.fromJson(Map<String, dynamic> j, [String path = 'source.building']) {
    final c = j['outline_centroid'];
    return RoofBuilding(
      parcelId: j['parcel_id'] is String ? j['parcel_id'] as String : null,
      outlineId: j['outline_id'] == null ? null : '${j['outline_id']}',
      outlineCentroid: c == null ? null : asPt(c, '$path.outline_centroid'),
      chosenBy: j['chosen_by'] is String ? j['chosen_by'] as String : null,
    );
  }

  final String? parcelId, outlineId;

  /// A point inside the chosen outline as `(x: lat, y: lng)`, WGS84.
  final Pt? outlineCentroid;

  /// `auto` or `user`.
  final String? chosenBy;

  Map<String, dynamic> toJson() => {
        if (parcelId != null) 'parcel_id': parcelId,
        if (outlineId != null) 'outline_id': outlineId,
        if (outlineCentroid != null) 'outline_centroid': ptJson(outlineCentroid!),
        if (chosenBy != null) 'chosen_by': chosenBy,
      };
}
