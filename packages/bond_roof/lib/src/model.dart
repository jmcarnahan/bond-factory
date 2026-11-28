import 'dart:math' as math;

import 'json_util.dart';
import 'quality.dart';
import 'model_parts.dart';
import 'totals.dart';

export 'engine_totals.dart';
export 'model_parts.dart';
export 'quality.dart';
export 'totals.dart';

class RoofModel {
  const RoofModel({
    this.schema = 'bond.roof_model/0.1',
    this.address = const RoofAddress(),
    this.source = const RoofSource(method: 'unknown'),
    this.facets = const [],
    this.edges = const [],
    this.holes = const [],
    this.objects = const [],
    required this.totals,
    this.confidence = const RoofConfidence(),
    this.warnings = const [],
    this.extra = const {},
    this.parseNotes = const [],
  });

  /// Parses the contract JSON (schema `bond.roof_model/0.x`).
  ///
  /// Throws [FormatException] whose message starts with the JSON path of the problem. Values a
  /// newer or older service may send are tolerated: an unknown edge type reads as `unspecified`, an
  /// unknown facet kind is chosen from the pitch, an unknown object kind reads as `unknown`, and an
  /// unknown `lengths_ft` key lands in [RoofTotals.extraLengths]. Each mapping is recorded in
  /// [parseNotes]. A model of the OLD block shape (`blocks`, `from_planes`, `source.solar`;
  /// the 0.6.0 engine writes none of them, only old stored results carry them) still parses: the keys this package
  /// no longer models are kept in [extra] and written back.
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

    final facets = items('facets', (j, p) => RoofFacet.fromJson(j, p, notes));
    final edges = items('edges', (j, p) => RoofEdge.fromJson(j, p, notes));
    final holes = items('holes', RoofHole.fromJson);
    final objects = <RoofObject>[];
    if (json['objects'] != null) {
      if (json['objects'] is! List) {
        notes.add('objects: expected an array, ignored');
      } else {
        final l = json['objects'] as List;
        for (var i = 0; i < l.length; i++) {
          try {
            objects.add(RoofObject.fromJson(asMap(l[i], 'objects[$i]'), 'objects[$i]', notes));
          } on FormatException catch (e) {
            notes.add('objects[$i]: skipped, ${e.message}');
          }
        }
      }
    }
    final box = _boundsOf(facets, edges, holes);
    for (final (i, o) in objects.indexed) {
      if (!_nearRoof(box, o)) notes.add('objects[$i]: centre is outside the roof, not drawn');
    }
    return RoofModel(
      schema: schema,
      address: json['address'] == null ? const RoofAddress() : RoofAddress.fromJson(asMap(json['address'], 'address')),
      source: json['source'] == null
          ? const RoofSource(method: 'unknown')
          : RoofSource.fromJson(asMap(json['source'], 'source')),
      facets: facets,
      edges: edges,
      holes: holes,
      objects: objects,
      totals: json['totals'] == null
          ? RoofTotals.recompute(facets, edges)
          : RoofTotals.fromJson(asMap(json['totals'], 'totals'), facets, edges, 'totals', notes),
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
    'schema', 'address', 'source', 'facets', 'edges', 'holes', 'objects', 'totals', 'confidence', 'warnings',
  };

  final String schema;
  final RoofAddress address;
  final RoofSource source;
  final List<RoofFacet> facets;
  final List<RoofEdge> edges;
  final List<RoofHole> holes;

  /// What stands on the roof (chimneys, lanterns). Never a facet, never in an area. Empty when the service sends none.
  final List<RoofObject> objects;
  final RoofTotals totals;
  final RoofConfidence confidence;
  final List<String> warnings;

  /// Top-level fields this package does not model (generated_at, origin, north_deg, units, debug).
  final Map<String, dynamic> extra;

  /// One line per value the tolerant parser mapped instead of rejecting (empty for a model that
  /// only uses known values). Not written back by [toJson].
  final List<String> parseNotes;

  bool get _anyRoofType => facets.any((f) => f.roofType != null);

  /// Flat area (sq ft) as the drawing hatches it: the sum over facets typed `flat` when any facet has a roof type
  /// (envelope 0.4+), else the totals' own value (a 0.1 model, or one without roof types). The totals cut flat at 0.5/12
  /// by contract, so a facet typed flat at a higher pitch is counted here and not there.
  double get flatAreaSqftByRoofType =>
      _anyRoofType ? facets.where((f) => f.isFlatRoofType).fold(0.0, (a, f) => a + f.areaSqft) : totals.flatAreaSqft;

  /// Pitched area (sq ft), never below 0: the total minus [flatAreaSqftByRoofType] when facets carry roof types, else the totals' value.
  double get pitchedAreaSqftByRoofType =>
      _anyRoofType ? math.max(0.0, totals.totalAreaSqft - flatAreaSqftByRoofType) : totals.pitchedAreaSqft;

  Map<String, dynamic> toJson() => {
        'schema': schema,
        ...{for (final e in extra.entries) if (e.key == 'generated_at') e.key: e.value},
        'address': address.toJson(),
        ...{for (final e in extra.entries) if (e.key == 'origin' || e.key == 'north_deg' || e.key == 'units') e.key: e.value},
        'source': source.toJson(),
        'facets': [for (final f in facets) f.toJson()],
        'edges': [for (final e in edges) e.toJson()],
        'holes': [for (final h in holes) h.toJson()],
        if (objects.isNotEmpty) 'objects': [for (final o in objects) o.toJson()],
        'totals': totals.toJson(),
        'confidence': confidence.toJson(),
        'warnings': warnings,
        ...{
          for (final e in extra.entries)
            if (!const {'generated_at', 'origin', 'north_deg', 'units'}.contains(e.key)) e.key: e.value
        },
      };

  /// The `quality` block of envelope 0.4 (null when the model has none), read from [extra].
  RoofEngineQuality? get quality => extra['quality'] is Map ? RoofEngineQuality.fromJson(asMap(extra['quality'], 'quality')) : null;

  /// The `source.building` block of envelope 0.4 (null when absent).
  RoofBuilding? get building =>
      source.raw['building'] is Map ? RoofBuilding.fromJson(asMap(source.raw['building'], 'source.building')) : null;

  /// Recomputes the totals from facets and edges with the contract's rules (see
  /// [RoofTotals.recompute]).
  RoofTotals recomputeTotals() => RoofTotals.recompute(facets, edges);

  /// True when [o] stands on the roof (its centre within [objectMargin] feet of the geometry). An object off the roof, or on
  /// a model with no geometry at all, is kept in [objects] but never drawn.
  bool objectOnRoof(RoofObject o) => _nearRoof(_boundsOf(facets, edges, holes), o);

  /// Bounding box of every point in the model (edges, facets, holes).
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
    for (final h in holes) {
      h.polygon.forEach(add);
    }
    if (minX > maxX) return (min: (x: 0.0, y: 0.0), max: (x: 0.0, y: 0.0));
    return (min: (x: minX, y: minY), max: (x: maxX, y: maxY));
  }
}

/// How far outside the roof geometry an object's centre may be and still be drawn, feet.
const double objectMargin = 5.0;

({double minX, double minY, double maxX, double maxY})? _boundsOf(List<RoofFacet> facets, List<RoofEdge> edges, List<RoofHole> holes) {
  var minX = double.infinity, minY = double.infinity, maxX = -double.infinity, maxY = -double.infinity;
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
  for (final h in holes) {
    h.polygon.forEach(add);
  }
  return minX > maxX ? null : (minX: minX, minY: minY, maxX: maxX, maxY: maxY);
}

bool _nearRoof(({double minX, double minY, double maxX, double maxY})? b, RoofObject o) =>
    b != null &&
    o.center.x >= b.minX - objectMargin &&
    o.center.x <= b.maxX + objectMargin &&
    o.center.y >= b.minY - objectMargin &&
    o.center.y <= b.maxY + objectMargin;
