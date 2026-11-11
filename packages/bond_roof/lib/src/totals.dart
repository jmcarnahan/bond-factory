import 'json_util.dart';
import 'model_parts.dart';

class RoofTotals {
  const RoofTotals({
    required this.totalAreaSqft,
    required this.pitchedAreaSqft,
    required this.flatAreaSqft,
    required this.predominantPitchRise,
    required this.predominantPitchAreaSqft,
    required this.squares,
    required this.lengthsFt,
    this.extraLengths = const {},
  });

  /// Tolerant: a `lengths_ft` key that is not one of the ten edge types is kept in
  /// [extraLengths] and noted in [notes] instead of throwing.
  factory RoofTotals.fromJson(Map<String, dynamic> j, [String path = 'totals', List<String>? notes]) {
    final raw = j['lengths_ft'] == null ? <String, dynamic>{} : asMap(j['lengths_ft'], '$path.lengths_ft');
    final extra = <String, double>{};
    for (final e in raw.entries) {
      if (EdgeType.values.any((t) => t.json == e.key)) continue;
      extra[e.key] = asNum(e.value, '$path.lengths_ft.${e.key}');
      notes?.add('$path.lengths_ft.${e.key}: unknown edge type, kept in extraLengths');
    }
    final total = asNum(j['total_area_sqft'], '$path.total_area_sqft');
    return RoofTotals(
      totalAreaSqft: total,
      pitchedAreaSqft: numOr(j, 'pitched_area_sqft', path, 0),
      flatAreaSqft: numOr(j, 'flat_area_sqft', path, 0),
      predominantPitchRise: numOr(j, 'predominant_pitch_rise', path, 0),
      predominantPitchAreaSqft: numOr(j, 'predominant_pitch_area_sqft', path, 0),
      squares: numOr(j, 'squares', path, total / 100),
      lengthsFt: {
        for (final t in EdgeType.values)
          t: raw[t.json] == null ? 0.0 : asNum(raw[t.json], '$path.lengths_ft.${t.json}'),
      },
      extraLengths: extra,
    );
  }

  /// Recomputes the totals from facets and edges with the contract's rules:
  /// areas sum `area_sqft` (holes are already subtracted there), pitched/flat split by facet
  /// kind, predominant pitch is the half-pitch bucket with the largest summed area (ties: lower
  /// pitch), lengths sum `length_ft` per edge type.
  factory RoofTotals.recompute(List<RoofFacet> facets, List<RoofEdge> edges) {
    var total = 0.0, pitched = 0.0, flat = 0.0;
    final area = <double, double>{}; // pitch key -> summed area
    for (final f in facets) {
      total += f.areaSqft;
      final isFlat = f.kind == FacetKind.flat;
      if (isFlat) {
        flat += f.areaSqft;
      } else {
        pitched += f.areaSqft;
      }
      final key = isFlat || f.pitchRise <= 0.5 ? 0.0 : (f.pitchRise * 2).round() / 2;
      area[key] = (area[key] ?? 0) + f.areaSqft;
    }
    // Flat is bucket 0. Ties go to the lower pitch (buckets are visited in ascending order,
    // strict greater wins).
    var bestKey = 0.0, bestArea = 0.0;
    for (final key in (area.keys.toList()..sort())) {
      if (area[key]! > bestArea) {
        bestArea = area[key]!;
        bestKey = key;
      }
    }
    final lengths = {for (final t in EdgeType.values) t: 0.0};
    for (final e in edges) {
      lengths[e.type] = lengths[e.type]! + e.lengthFt;
    }
    return RoofTotals(
      totalAreaSqft: total,
      pitchedAreaSqft: pitched,
      flatAreaSqft: flat,
      predominantPitchRise: bestKey,
      predominantPitchAreaSqft: bestArea,
      squares: total / 100,
      lengthsFt: lengths,
    );
  }

  final double totalAreaSqft, pitchedAreaSqft, flatAreaSqft, predominantPitchRise, predominantPitchAreaSqft, squares;

  /// Always holds all ten edge types, zero when absent.
  final Map<EdgeType, double> lengthsFt;

  /// `lengths_ft` keys this package does not know (a newer service may add edge types).
  final Map<String, double> extraLengths;

  Map<String, dynamic> toJson() => {
        'total_area_sqft': totalAreaSqft,
        'pitched_area_sqft': pitchedAreaSqft,
        'flat_area_sqft': flatAreaSqft,
        'predominant_pitch_rise': predominantPitchRise,
        'predominant_pitch_area_sqft': predominantPitchAreaSqft,
        'squares': squares,
        'lengths_ft': {for (final t in EdgeType.values) t.json: lengthsFt[t] ?? 0.0, ...extraLengths},
      };
}
