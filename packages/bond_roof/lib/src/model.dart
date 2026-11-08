import 'dart:math' as math;

/// A point in feet (model space: x east, y north) or in pixels (scene space: y down).
typedef Pt = ({double x, double y});

enum EdgeType {
  eave('eave'),
  rake('rake'),
  ridge('ridge'),
  hip('hip'),
  valley('valley'),
  stepFlashing('step_flashing'),
  wallFlashing('wall_flashing'),
  parapet('parapet'),
  transition('transition'),
  unspecified('unspecified');

  const EdgeType(this.json);

  /// The name used in the JSON contract.
  final String json;
}

enum FacetKind {
  flat('flat'),
  sloped('sloped');

  const FacetKind(this.json);
  final String json;
}

enum BlockForm {
  flat('flat'),
  hip('hip'),
  gable('gable'),
  shed('shed');

  const BlockForm(this.json);
  final String json;
}

// ---------------------------------------------------------------- parsing helpers

Never _bad(String path, String msg) => throw FormatException('$path: $msg');

Map<String, dynamic> _map(Object? v, String path) {
  if (v is Map<String, dynamic>) return v;
  if (v is Map) return v.map((k, x) => MapEntry('$k', x));
  _bad(path, 'expected an object');
}

List<Object?> _list(Object? v, String path) {
  if (v is List) return v;
  _bad(path, 'expected an array');
}

double _num(Object? v, String path) {
  if (v is num && v.isFinite) return v.toDouble();
  _bad(path, 'expected a finite number');
}

double _numOr(Map<String, dynamic> m, String key, String path, double fallback) =>
    m[key] == null ? fallback : _num(m[key], '$path.$key');

double? _numOrNull(Map<String, dynamic> m, String key, String path) =>
    m[key] == null ? null : _num(m[key], '$path.$key');

String _str(Object? v, String path) {
  if (v is String) return v;
  _bad(path, 'expected a string');
}

String _strOr(Map<String, dynamic> m, String key, String path, String fallback) =>
    m[key] == null ? fallback : _str(m[key], '$path.$key');

Pt _pt(Object? v, String path) {
  if (v is List && v.length == 2) {
    return (x: _num(v[0], '$path[0]'), y: _num(v[1], '$path[1]'));
  }
  _bad(path, 'expected [x, y]');
}

List<Pt> _poly(Object? v, String path) {
  final l = _list(v, path);
  if (l.length < 3) _bad(path, 'a polygon needs at least 3 points');
  return [for (var i = 0; i < l.length; i++) _pt(l[i], '$path[$i]')];
}

List<Object?> _ptJson(Pt p) => [p.x, p.y];
List<Object?> _polyJson(List<Pt> p) => [for (final q in p) _ptJson(q)];

T _enum<T>(String s, List<T> values, String Function(T) name, String path) {
  for (final v in values) {
    if (name(v) == s) return v;
  }
  _bad(path, 'unknown value "$s" (expected one of ${values.map(name).join(', ')})');
}

// ---------------------------------------------------------------- model classes

class RoofAddress {
  const RoofAddress({
    this.line1 = '',
    this.city = '',
    this.state = '',
    this.zip = '',
    this.formatted = '',
  });

  factory RoofAddress.fromJson(Map<String, dynamic> j, [String path = 'address']) => RoofAddress(
        line1: _strOr(j, 'line1', path, ''),
        city: _strOr(j, 'city', path, ''),
        state: _strOr(j, 'state', path, ''),
        zip: _strOr(j, 'zip', path, ''),
        formatted: _strOr(j, 'formatted', path, ''),
      );

  final String line1, city, state, zip, formatted;

  /// The best single-line description available.
  String get display {
    if (formatted.isNotEmpty) return formatted;
    final parts = [line1, city, [state, zip].where((s) => s.isNotEmpty).join(' ')];
    return parts.where((s) => s.isNotEmpty).join(', ');
  }

  Map<String, dynamic> toJson() =>
      {'line1': line1, 'city': city, 'state': state, 'zip': zip, 'formatted': formatted};
}

class RoofSource {
  const RoofSource({required this.method, this.raw = const {}});

  factory RoofSource.fromJson(Map<String, dynamic> j, [String path = 'source']) =>
      RoofSource(method: _strOr(j, 'method', path, 'unknown'), raw: Map.of(j));

  final String method;

  /// The whole "source" object, kept so provider, LiDAR and Solar details survive a round trip.
  final Map<String, dynamic> raw;

  Map<String, dynamic> toJson() => {...raw, 'method': method};
}

class RoofBlock {
  const RoofBlock({
    required this.id,
    required this.form,
    required this.polygon,
    this.pitchRise = 0,
    this.gableEdges = const [],
    this.extra = const {},
  });

  factory RoofBlock.fromJson(Map<String, dynamic> j, String path) => RoofBlock(
        id: _str(j['id'], '$path.id'),
        form: _enum(_str(j['form'], '$path.form'), BlockForm.values, (v) => v.json, '$path.form'),
        polygon: _poly(j['polygon'], '$path.polygon'),
        pitchRise: _numOr(j, 'pitch_rise', path, 0),
        gableEdges: j['gable_edges'] == null
            ? const []
            : [
                for (final (i, v) in _list(j['gable_edges'], '$path.gable_edges').indexed)
                  _num(v, '$path.gable_edges[$i]').toInt()
              ],
        extra: {
          for (final e in j.entries)
            if (!_blockKnown.contains(e.key)) e.key: e.value
        },
      );

  static const _blockKnown = {'id', 'form', 'polygon', 'pitch_rise', 'gable_edges'};

  final String id;
  final BlockForm form;
  final List<Pt> polygon;
  final double pitchRise;
  final List<int> gableEdges;

  /// Other contract fields (ridge_azimuth_deg, eave_height_ft, plan_area_sqft), kept verbatim.
  final Map<String, dynamic> extra;

  Map<String, dynamic> toJson() => {
        'id': id,
        'form': form.json,
        'polygon': _polyJson(polygon),
        'pitch_rise': pitchRise,
        'gable_edges': gableEdges,
        ...extra,
      };
}

class RoofFacet {
  const RoofFacet({
    required this.id,
    required this.block,
    required this.kind,
    required this.polygon,
    required this.pitchRise,
    this.aspectDeg,
    required this.planAreaSqft,
    required this.areaSqft,
  });

  factory RoofFacet.fromJson(Map<String, dynamic> j, String path) {
    final area = _num(j['area_sqft'], '$path.area_sqft');
    return RoofFacet(
      id: _str(j['id'], '$path.id'),
      block: _strOr(j, 'block', path, ''),
      kind: _enum(_str(j['kind'], '$path.kind'), FacetKind.values, (v) => v.json, '$path.kind'),
      polygon: _poly(j['polygon'], '$path.polygon'),
      pitchRise: _numOr(j, 'pitch_rise', path, 0),
      aspectDeg: _numOrNull(j, 'aspect_deg', path),
      planAreaSqft: _numOr(j, 'plan_area_sqft', path, area),
      areaSqft: area,
    );
  }

  final String id, block;
  final FacetKind kind;
  final List<Pt> polygon;
  final double pitchRise;
  final double? aspectDeg;
  final double planAreaSqft, areaSqft;

  Map<String, dynamic> toJson() => {
        'id': id,
        'block': block,
        'kind': kind.json,
        'polygon': _polyJson(polygon),
        'pitch_rise': pitchRise,
        'aspect_deg': aspectDeg,
        'plan_area_sqft': planAreaSqft,
        'area_sqft': areaSqft,
      };
}

class RoofEdge {
  const RoofEdge({
    required this.id,
    required this.type,
    required this.a,
    required this.b,
    required this.lengthFt,
    this.facets = const [],
  });

  factory RoofEdge.fromJson(Map<String, dynamic> j, String path) {
    final pts = _list(j['points'], '$path.points');
    if (pts.length != 2) _bad('$path.points', 'an edge has exactly two points');
    final a = _pt(pts[0], '$path.points[0]');
    final b = _pt(pts[1], '$path.points[1]');
    return RoofEdge(
      id: _str(j['id'], '$path.id'),
      type: _enum(_str(j['type'], '$path.type'), EdgeType.values, (v) => v.json, '$path.type'),
      a: a,
      b: b,
      lengthFt: _numOr(j, 'length_ft', path, math.sqrt(math.pow(b.x - a.x, 2) + math.pow(b.y - a.y, 2))),
      facets: j['facets'] == null
          ? const []
          : [
              for (final (i, v) in _list(j['facets'], '$path.facets').indexed)
                _str(v, '$path.facets[$i]')
            ],
    );
  }

  final String id;
  final EdgeType type;
  final Pt a, b;
  final double lengthFt;
  final List<String> facets;

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.json,
        'points': [_ptJson(a), _ptJson(b)],
        'length_ft': lengthFt,
        'facets': facets,
      };
}

class RoofHole {
  const RoofHole({required this.id, required this.kind, required this.polygon, required this.areaSqft});

  factory RoofHole.fromJson(Map<String, dynamic> j, String path) => RoofHole(
        id: _str(j['id'], '$path.id'),
        kind: _strOr(j, 'kind', path, 'hole'),
        polygon: _poly(j['polygon'], '$path.polygon'),
        areaSqft: _numOr(j, 'area_sqft', path, 0),
      );

  final String id, kind;
  final List<Pt> polygon;
  final double areaSqft;

  Map<String, dynamic> toJson() =>
      {'id': id, 'kind': kind, 'polygon': _polyJson(polygon), 'area_sqft': areaSqft};
}

class RoofTotals {
  const RoofTotals({
    required this.totalAreaSqft,
    required this.pitchedAreaSqft,
    required this.flatAreaSqft,
    required this.predominantPitchRise,
    required this.predominantPitchAreaSqft,
    required this.squares,
    required this.lengthsFt,
  });

  factory RoofTotals.fromJson(Map<String, dynamic> j, [String path = 'totals']) {
    final raw = j['lengths_ft'] == null ? <String, dynamic>{} : _map(j['lengths_ft'], '$path.lengths_ft');
    for (final k in raw.keys) {
      if (!EdgeType.values.any((t) => t.json == k)) _bad('$path.lengths_ft.$k', 'unknown edge type');
    }
    final total = _num(j['total_area_sqft'], '$path.total_area_sqft');
    return RoofTotals(
      totalAreaSqft: total,
      pitchedAreaSqft: _numOr(j, 'pitched_area_sqft', path, 0),
      flatAreaSqft: _numOr(j, 'flat_area_sqft', path, 0),
      predominantPitchRise: _numOr(j, 'predominant_pitch_rise', path, 0),
      predominantPitchAreaSqft: _numOr(j, 'predominant_pitch_area_sqft', path, 0),
      squares: _numOr(j, 'squares', path, total / 100),
      lengthsFt: {
        for (final t in EdgeType.values)
          t: raw[t.json] == null ? 0.0 : _num(raw[t.json], '$path.lengths_ft.${t.json}'),
      },
    );
  }

  final double totalAreaSqft, pitchedAreaSqft, flatAreaSqft, predominantPitchRise, predominantPitchAreaSqft, squares;

  /// Always holds all ten edge types, zero when absent.
  final Map<EdgeType, double> lengthsFt;

  Map<String, dynamic> toJson() => {
        'total_area_sqft': totalAreaSqft,
        'pitched_area_sqft': pitchedAreaSqft,
        'flat_area_sqft': flatAreaSqft,
        'predominant_pitch_rise': predominantPitchRise,
        'predominant_pitch_area_sqft': predominantPitchAreaSqft,
        'squares': squares,
        'lengths_ft': {for (final t in EdgeType.values) t.json: lengthsFt[t] ?? 0.0},
      };
}

class RoofConfidence {
  const RoofConfidence({this.overall = 'unknown', this.notes = const []});

  factory RoofConfidence.fromJson(Map<String, dynamic> j, [String path = 'confidence']) => RoofConfidence(
        overall: _strOr(j, 'overall', path, 'unknown'),
        notes: j['notes'] == null
            ? const []
            : [for (final (i, v) in _list(j['notes'], '$path.notes').indexed) _str(v, '$path.notes[$i]')],
      );

  final String overall;
  final List<String> notes;

  Map<String, dynamic> toJson() => {'overall': overall, 'notes': notes};
}

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
  });

  /// Parses the contract JSON (schema `bond.roof_model/0.x`).
  /// Throws [FormatException] whose message starts with the JSON path of the problem.
  factory RoofModel.fromJson(Map<String, dynamic> json) {
    final schema = _str(json['schema'], 'schema');
    if (!schema.startsWith('bond.roof_model/0.')) _bad('schema', 'unsupported schema "$schema"');
    if (json['units'] != null && json['units'] != 'ft') {
      _bad('units', 'unsupported units "${json['units']}" (only "ft")');
    }

    List<T> items<T>(String key, T Function(Map<String, dynamic>, String) f) {
      if (json[key] == null) return <T>[];
      final l = _list(json[key], key);
      return [for (var i = 0; i < l.length; i++) f(_map(l[i], '$key[$i]'), '$key[$i]')];
    }

    final blocks = items('blocks', RoofBlock.fromJson);
    final facets = items('facets', RoofFacet.fromJson);
    final edges = items('edges', RoofEdge.fromJson);
    final holes = items('holes', RoofHole.fromJson);
    final partial = RoofModel(
      schema: schema,
      blocks: blocks,
      facets: facets,
      edges: edges,
      totals: _emptyTotals,
    );
    return RoofModel(
      schema: schema,
      address: json['address'] == null ? const RoofAddress() : RoofAddress.fromJson(_map(json['address'], 'address')),
      source: json['source'] == null
          ? const RoofSource(method: 'unknown')
          : RoofSource.fromJson(_map(json['source'], 'source')),
      blocks: blocks,
      facets: facets,
      edges: edges,
      holes: holes,
      totals: json['totals'] == null ? partial.recomputeTotals() : RoofTotals.fromJson(_map(json['totals'], 'totals')),
      confidence: json['confidence'] == null
          ? const RoofConfidence()
          : RoofConfidence.fromJson(_map(json['confidence'], 'confidence')),
      warnings: json['warnings'] == null
          ? const []
          : [for (final (i, v) in _list(json['warnings'], 'warnings').indexed) _str(v, 'warnings[$i]')],
      extra: {
        for (final e in json.entries)
          if (!_known.contains(e.key)) e.key: e.value
      },
    );
  }

  static const _known = {
    'schema', 'address', 'source', 'blocks', 'facets', 'edges', 'holes', 'totals', 'confidence', 'warnings',
  };

  static const _emptyTotals = RoofTotals(
    totalAreaSqft: 0,
    pitchedAreaSqft: 0,
    flatAreaSqft: 0,
    predominantPitchRise: 0,
    predominantPitchAreaSqft: 0,
    squares: 0,
    lengthsFt: {},
  );

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

  /// Recomputes the totals from facets and edges with the contract's rules:
  /// areas sum `area_sqft` (holes are already subtracted there), pitched/flat split by facet
  /// kind, predominant pitch is the half-pitch bucket with the largest summed area (ties: lower pitch), lengths
  /// sum `length_ft` per edge type.
  RoofTotals recomputeTotals() {
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
    // Predominant pitch is the half-pitch bucket with the largest summed area; flat is bucket 0.
    // Ties go to the lower pitch (buckets are visited in ascending order, strict greater wins).
    var bestKey = 0.0, bestArea = 0.0;
    for (final key in (area.keys.toList()..sort())) {
      if (area[key]! > bestArea) {
        bestArea = area[key]!;
        bestKey = key;
      }
    }
    final rise = bestKey;
    final lengths = {for (final t in EdgeType.values) t: 0.0};
    for (final e in edges) {
      lengths[e.type] = lengths[e.type]! + e.lengthFt;
    }
    return RoofTotals(
      totalAreaSqft: total,
      pitchedAreaSqft: pitched,
      flatAreaSqft: flat,
      predominantPitchRise: rise,
      predominantPitchAreaSqft: bestArea,
      squares: total / 100,
      lengthsFt: lengths,
    );
  }

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
