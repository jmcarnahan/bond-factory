import 'dart:math' as math;

import 'json_util.dart';
import 'model_parts.dart';
import 'totals.dart';

export 'model_parts.dart';
export 'totals.dart';

class RoofModel {
  const RoofModel({
    this.schema = 'bond.roof_model/0.1',
    this.address = const RoofAddress(),
    this.source = const RoofSource(method: 'unknown'),
    this.blocks = const [],
    this.facets = const [],
    this.edges = const [],
    this.holes = const [],
    required this.totals,
    this.confidence = const RoofConfidence(),
    this.warnings = const [],
    this.extra = const {},
    this.parseNotes = const [],
  });

  /// Parses the contract JSON (schema `bond.roof_model/0.x`).
  ///
  /// Throws [FormatException] whose message starts with the JSON path of the problem. Values a
  /// newer service may add are tolerated: an unknown edge type reads as `unspecified`, an
  /// unknown facet kind is chosen from the pitch, an unknown block form reads as `flat`, and an
  /// unknown `lengths_ft` key lands in [RoofTotals.extraLengths]. Each mapping is recorded in
  /// [parseNotes].
  factory RoofModel.fromJson(Map<String, dynamic> json) {
    final schema = asStr(json['schema'], 'schema');
    if (!schema.startsWith('bond.roof_model/0.')) badJson('schema', 'unsupported schema "$schema"');
    if (json['units'] != null && json['units'] != 'ft') {
      badJson('units', 'unsupported units "${json['units']}" (only "ft")');
    }
    final notes = <String>[];

    List<T> items<T>(String key, T Function(Map<String, dynamic>, String) f) {
      if (json[key] == null) return <T>[];
      final l = asList(json[key], key);
      return [for (var i = 0; i < l.length; i++) f(asMap(l[i], '$key[$i]'), '$key[$i]')];
    }

    final blocks = items('blocks', (j, p) => RoofBlock.fromJson(j, p, notes));
    final facets = items('facets', (j, p) => RoofFacet.fromJson(j, p, notes));
    final edges = items('edges', (j, p) => RoofEdge.fromJson(j, p, notes));
    final holes = items('holes', RoofHole.fromJson);
    return RoofModel(
      schema: schema,
      address: json['address'] == null ? const RoofAddress() : RoofAddress.fromJson(asMap(json['address'], 'address')),
      source: json['source'] == null
          ? const RoofSource(method: 'unknown')
          : RoofSource.fromJson(asMap(json['source'], 'source')),
      blocks: blocks,
      facets: facets,
      edges: edges,
      holes: holes,
      totals: json['totals'] == null
          ? RoofTotals.recompute(facets, edges)
          : RoofTotals.fromJson(asMap(json['totals'], 'totals'), 'totals', notes),
      confidence: json['confidence'] == null
          ? const RoofConfidence()
          : RoofConfidence.fromJson(asMap(json['confidence'], 'confidence')),
      warnings: strList(json['warnings'], 'warnings'),
      extra: {
        for (final e in json.entries)
          if (!_known.contains(e.key)) e.key: e.value
      },
      parseNotes: List.unmodifiable(notes),
    );
  }

  static const _known = {
    'schema', 'address', 'source', 'blocks', 'facets', 'edges', 'holes', 'totals', 'confidence', 'warnings',
  };

  final String schema;
  final RoofAddress address;
  final RoofSource source;
  final List<RoofBlock> blocks;
  final List<RoofFacet> facets;
  final List<RoofEdge> edges;
  final List<RoofHole> holes;
  final RoofTotals totals;
  final RoofConfidence confidence;
  final List<String> warnings;

  /// Top-level fields this package does not model (generated_at, origin, north_deg, units, debug).
  final Map<String, dynamic> extra;

  /// One line per value the tolerant parser mapped instead of rejecting (empty for a model that
  /// only uses known values). Not written back by [toJson].
  final List<String> parseNotes;

  Map<String, dynamic> toJson() => {
        'schema': schema,
        ...{for (final e in extra.entries) if (e.key == 'generated_at') e.key: e.value},
        'address': address.toJson(),
        ...{for (final e in extra.entries) if (e.key == 'origin' || e.key == 'north_deg' || e.key == 'units') e.key: e.value},
        'source': source.toJson(),
        'blocks': [for (final b in blocks) b.toJson()],
        'facets': [for (final f in facets) f.toJson()],
        'edges': [for (final e in edges) e.toJson()],
        'holes': [for (final h in holes) h.toJson()],
        'totals': totals.toJson(),
        'confidence': confidence.toJson(),
        'warnings': warnings,
        ...{
          for (final e in extra.entries)
            if (!const {'generated_at', 'origin', 'north_deg', 'units'}.contains(e.key)) e.key: e.value
        },
      };

  /// Recomputes the totals from facets and edges with the contract's rules (see
  /// [RoofTotals.recompute]).
  RoofTotals recomputeTotals() => RoofTotals.recompute(facets, edges);

  /// Bounding box of every point in the model (edges, facets, blocks, holes).
  ({Pt min, Pt max}) get bounds {
    var minX = double.infinity, minY = double.infinity;
    var maxX = -double.infinity, maxY = -double.infinity;
    void add(Pt p) {
      minX = math.min(minX, p.x);
      maxX = math.max(maxX, p.x);
      minY = math.min(minY, p.y);
      maxY = math.max(maxY, p.y);
    }

    for (final e in edges) {
      add(e.a);
      add(e.b);
    }
    for (final f in facets) {
      f.polygon.forEach(add);
    }
    for (final b in blocks) {
      b.polygon.forEach(add);
    }
    for (final h in holes) {
      h.polygon.forEach(add);
    }
    if (minX > maxX) return (min: (x: 0.0, y: 0.0), max: (x: 0.0, y: 0.0));
    return (min: (x: minX, y: minY), max: (x: maxX, y: maxY));
  }
}
