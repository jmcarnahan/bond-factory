import 'dart:math' as math;

import 'engine_totals.dart';
import 'json_util.dart';
import 'model_parts.dart';

/// `model.totals`: the model's own sums, always present (read from the JSON, else recomputed from the facets and edges),
/// plus the 0.6 keys when the totals carry them ([engine]).
class RoofTotals {
  const RoofTotals({
    required this.totalAreaSqft,
    required this.pitchedAreaSqft,
    required this.flatAreaSqft,
    required this.squares,
    required this.lengthsFt,
    this.extraLengths = const {},
    this.engine,
  });

  /// Tolerant: a `lengths_ft` key that is not one of the edge types is kept in [extraLengths] and noted in [notes]
  /// instead of throwing. A sum the JSON leaves out is recomputed from [facets] and [edges] (a service that writes only
  /// the 0.6 keys, or an old model, still parses).
  factory RoofTotals.fromJson(
    Map<String, dynamic> j,
    List<RoofFacet> facets,
    List<RoofEdge> edges, [
    String path = 'totals',
    List<String>? notes,
  ]) {
    final r = RoofTotals.recompute(facets, edges);
    final raw = j['lengths_ft'] == null ? <String, dynamic>{} : asMap(j['lengths_ft'], '$path.lengths_ft');
    final extra = <String, double>{};
    for (final e in raw.entries) {
      if (EdgeType.values.any((t) => t.json == e.key)) continue;
      // `parapet` stays valid in the schema for stored results; the engine writes it as 0 and emits no such edge.
      if (e.key == 'parapet' && e.value == 0) continue;
      extra[e.key] = asNum(e.value, '$path.lengths_ft.${e.key}');
      notes?.add('$path.lengths_ft.${e.key}: unknown edge type, kept in extraLengths');
    }
    final total = numOr(j, 'total_area_sqft', path, numOr(j, 'area_sqft', path, r.totalAreaSqft));
    return RoofTotals(
      totalAreaSqft: total,
      pitchedAreaSqft: numOr(j, 'pitched_area_sqft', path, r.pitchedAreaSqft),
      flatAreaSqft: numOr(j, 'flat_area_sqft', path, r.flatAreaSqft),
      squares: numOr(j, 'squares', path, total / 100),
      lengthsFt: {
        for (final t in EdgeType.values)
          t: raw[t.json] == null ? (raw.isEmpty ? r.lengthsFt[t]! : 0.0) : asNum(raw[t.json], '$path.lengths_ft.${t.json}'),
        // An edge of a type this package does not know is read as unspecified; its length is the drawn length, whatever
        // the totals say (they know it under its own name, which lands in [extraLengths]).
        EdgeType.unspecified: math.max(
            raw['unspecified'] == null ? 0.0 : asNum(raw['unspecified'], '$path.lengths_ft.unspecified'), r.lengthsFt[EdgeType.unspecified]!),
      },
      extraLengths: extra,
      engine: RoofEngineTotals.fromJson(j, path),
    );
  }

  /// Recomputes the totals from facets and edges: areas sum `area_sqft` (holes are already subtracted there), pitched
  /// and flat split by facet kind, lengths sum `length_ft` per edge type (a flat seam is drawn, never measured).
  factory RoofTotals.recompute(List<RoofFacet> facets, List<RoofEdge> edges) {
    var total = 0.0, pitched = 0.0, flat = 0.0;
    for (final f in facets) {
      total += f.areaSqft;
      if (f.kind == FacetKind.flat) {
        flat += f.areaSqft;
      } else {
        pitched += f.areaSqft;
      }
    }
    final lengths = {for (final t in EdgeType.values) t: 0.0};
    for (final e in edges) {
      if (e.type == EdgeType.flatSeam) continue;
      lengths[e.type] = lengths[e.type]! + e.lengthFt;
    }
    return RoofTotals(
      totalAreaSqft: total,
      pitchedAreaSqft: pitched,
      flatAreaSqft: flat,
      squares: total / 100,
      lengthsFt: lengths,
    );
  }

  /// The keys this class reads itself (the rest of `model.totals` is [RoofEngineTotals.knownKeys]).
  static const List<String> ownKeys = [
    'total_area_sqft', 'pitched_area_sqft', 'flat_area_sqft', 'squares', 'lengths_ft',
    // Model-only keys the engine still writes and this package does not read.
    'predominant_pitch_rise', 'predominant_pitch_area_sqft', 'note',
  ];

  final double totalAreaSqft, pitchedAreaSqft, flatAreaSqft, squares;

  /// Always holds every [EdgeType], zero when absent.
  final Map<EdgeType, double> lengthsFt;

  /// `lengths_ft` keys this package does not know (a newer service may add edge types).
  final Map<String, double> extraLengths;

  /// The 0.6 keys, when the model's `totals` carries any (null otherwise).
  final RoofEngineTotals? engine;

  Map<String, dynamic> toJson() => {
        'total_area_sqft': totalAreaSqft,
        'pitched_area_sqft': pitchedAreaSqft,
        'flat_area_sqft': flatAreaSqft,
        'squares': squares,
        'lengths_ft': {
          for (final t in EdgeType.values)
            if ((lengthsFt[t] ?? 0.0) != 0.0) t.json: lengthsFt[t]!,
          ...extraLengths,
        },
        ...?engine?.toJson(),
      };
}
