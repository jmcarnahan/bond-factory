import 'dart:math' as math;

import 'json_util.dart';

export 'json_util.dart' show Pt;
export 'model_facet.dart';

/// The edge types the engine emits (`docs/contract-0.6.md`) and [unspecified] for anything else.
enum EdgeType {
  /// Outer roof edge at the gutter line.
  eave('eave'),

  /// Outer roof edge up a gable end.
  rake('rake'),

  /// Outer edge of a low-slope section.
  flatEdge('flat_edge'),
  ridge('ridge'),
  hip('hip'),
  valley('valley'),

  /// A step that runs down the lower slope (the sidewall of the higher roof). Carries [RoofEdge.jumpFt].
  stepFlashing('step_flashing'),

  /// A step across the lower slope, or onto a low-slope section (the headwall). Carries [RoofEdge.jumpFt].
  wallFlashing('wall_flashing'),

  /// Pitched meets low-slope with no height step.
  transition('transition'),

  /// A step between two low-slope sections. Carries [RoofEdge.jumpFt].
  levelChange('level_change'),

  /// A seam between two flat sections at the same level: drawn as a thin dark line, never labelled, never priced, and
  /// its length is in no total or legend.
  flatSeam('flat_seam'),

  /// Any type this package does not know (a newer or older service).
  unspecified('unspecified');

  const EdgeType(this.json);

  /// The name used in the JSON contract.
  final String json;

  /// True for the three types whose edges carry a height step in feet.
  bool get hasJump => this == stepFlashing || this == wallFlashing || this == levelChange;
}

/// What stands on the roof (`model.objects`). It is never a facet and never in an area.
enum ObjectKind {
  chimney('chimney'),
  lantern('lantern'),

  /// Found but not classified: kept in the model, never drawn.
  unknown('unknown');

  const ObjectKind(this.json);
  final String json;
}

/// One entry of `model.objects`: a chimney or flue, a roof lantern, or something unclassified.
class RoofObject {
  const RoofObject({
    required this.id,
    required this.kind,
    required this.center,
    required this.sizeFt,
    this.polygon,
    this.heightFt,
    this.facet,
    this.returns,
  });

  /// Throws [FormatException] for an entry that cannot be read at all (no kind, no size and no polygon, a polygon of fewer
  /// than three points); [RoofModel.fromJson] skips such an entry with a parse note, since objects are decoration. An entry
  /// with a valid polygon and no (or a bad) `size_ft` takes its size, and a missing centre, from the polygon's bounding box.
  factory RoofObject.fromJson(Map<String, dynamic> j, String path, [List<String>? notes]) {
    final kindText = asStr(j['kind'], '$path.kind');
    var kind = enumOrNull(kindText, ObjectKind.values, (v) => v.json);
    if (kind == null) {
      kind = ObjectKind.unknown;
      notes?.add('$path.kind: unknown value "$kindText", read as unknown');
    }
    final polygon = j['polygon'] == null ? null : asPoly(j['polygon'], '$path.polygon');
    final box = polygon == null ? null : _bbox(polygon);
    (double, double)? size;
    try {
      if (j['size_ft'] != null) {
        final l = asList(j['size_ft'], '$path.size_ft');
        if (l.length != 2) badJson('$path.size_ft', 'expected [a, b]');
        size = (asNum(l[0], '$path.size_ft[0]'), asNum(l[1], '$path.size_ft[1]'));
      }
    } on FormatException {
      if (box == null) rethrow;
      notes?.add('$path.size_ft: unreadable, taken from the polygon');
    }
    if (size == null) {
      if (box == null) badJson('$path.size_ft', 'missing, and no polygon to take it from');
      size = (box.maxX - box.minX, box.maxY - box.minY);
    }
    final Pt center;
    if (j['center'] != null) {
      center = asPt(j['center'], '$path.center');
    } else if (box != null) {
      center = (x: (box.minX + box.maxX) / 2, y: (box.minY + box.maxY) / 2);
    } else {
      badJson('$path.center', 'missing');
    }
    return RoofObject(
      id: strOr(j, 'id', path, path),
      kind: kind,
      center: center,
      sizeFt: size,
      polygon: polygon,
      heightFt: numOrNull(j, 'height_ft', path),
      facet: j['facet'] is String ? j['facet'] as String : null,
      returns: numOrNull(j, 'returns', path)?.round(),
    );
  }

  static ({double minX, double maxX, double minY, double maxY}) _bbox(List<Pt> ps) => (
        minX: ps.map((p) => p.x).reduce(math.min),
        maxX: ps.map((p) => p.x).reduce(math.max),
        minY: ps.map((p) => p.y).reduce(math.min),
        maxY: ps.map((p) => p.y).reduce(math.max),
      );

  /// Perimeter in feet: of the polygon when there is one, else of the size rectangle.
  double get perimeterFt {
    final poly = polygon;
    if (poly == null) return 2 * (sizeFt.$1.abs() + sizeFt.$2.abs());
    var sum = 0.0;
    for (var i = 0; i < poly.length; i++) {
      final a = poly[i], b = poly[(i + 1) % poly.length];
      if (a == b) continue;
      sum += math.sqrt(math.pow(b.x - a.x, 2) + math.pow(b.y - a.y, 2));
    }
    return sum;
  }

  final String id;
  final ObjectKind kind;

  /// Centre in model feet (x east, y north).
  final Pt center;

  /// Footprint in feet: `a` along x (east), `b` along y (north).
  final (double, double) sizeFt;

  /// The footprint as measured (a rotated rectangle), model feet; null when the service sends only [sizeFt]. When present it
  /// is what is drawn.
  final List<Pt>? polygon;

  /// Height above the roof surface, feet, when measured.
  final double? heightFt;

  /// The facet it stands on, when known.
  final String? facet;

  /// LiDAR returns on the object.
  final int? returns;

  Map<String, dynamic> toJson() => {
        'id': id,
        'kind': kind.json,
        'center': ptJson(center),
        'size_ft': [sizeFt.$1, sizeFt.$2],
        if (polygon != null) 'polygon': polyJson(polygon!),
        if (heightFt != null) 'height_ft': heightFt,
        if (facet != null) 'facet': facet,
        if (returns != null) 'returns': returns,
      };
}

class RoofAddress {
  const RoofAddress({
    this.line1 = '',
    this.city = '',
    this.state = '',
    this.zip = '',
    this.formatted = '',
  });

  factory RoofAddress.fromJson(Map<String, dynamic> j, [String path = 'address']) => RoofAddress(
        line1: strOr(j, 'line1', path, ''),
        city: strOr(j, 'city', path, ''),
        state: strOr(j, 'state', path, ''),
        zip: strOr(j, 'zip', path, ''),
        formatted: strOr(j, 'formatted', path, ''),
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
      RoofSource(method: strOr(j, 'method', path, 'unknown'), raw: Map.of(j));

  final String method;

  /// The whole "source" object, kept so provider, LiDAR and Solar details survive a round trip.
  final Map<String, dynamic> raw;

  Map<String, dynamic> toJson() => {...raw, 'method': method};
}

/// Parsers below are tolerant: an unknown enum value is mapped to a safe one and the mapping is
/// appended to [notes] (when given) instead of throwing.
class RoofEdge {
  const RoofEdge({
    required this.id,
    required this.type,
    required this.a,
    required this.b,
    required this.lengthFt,
    this.facets = const [],
    this.jumpFt,
  });

  factory RoofEdge.fromJson(Map<String, dynamic> j, String path, [List<String>? notes]) {
    final pts = asList(j['points'], '$path.points');
    if (pts.length != 2) badJson('$path.points', 'an edge has exactly two points');
    final a = asPt(pts[0], '$path.points[0]');
    final b = asPt(pts[1], '$path.points[1]');
    final typeText = asStr(j['type'], '$path.type');
    var type = enumOrNull(typeText, EdgeType.values, (v) => v.json);
    if (type == null) {
      type = EdgeType.unspecified;
      notes?.add('$path.type: unknown value "$typeText", read as unspecified');
    }
    return RoofEdge(
      id: asStr(j['id'], '$path.id'),
      type: type,
      a: a,
      b: b,
      lengthFt: numOr(j, 'length_ft', path, math.sqrt(math.pow(b.x - a.x, 2) + math.pow(b.y - a.y, 2))),
      facets: strList(j['facets'], '$path.facets'),
      jumpFt: numOrNull(j, 'jump_ft', path),
    );
  }

  final String id;
  final EdgeType type;
  final Pt a, b;
  final double lengthFt;
  final List<String> facets;

  /// The height step in feet of a step edge ([EdgeType.hasJump]); null otherwise.
  final double? jumpFt;

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.json,
        'points': [ptJson(a), ptJson(b)],
        'length_ft': lengthFt,
        'facets': facets,
        if (jumpFt != null) 'jump_ft': jumpFt,
      };

  @override
  bool operator ==(Object other) =>
      other is RoofEdge &&
      other.id == id &&
      other.type == type &&
      other.a == a &&
      other.b == b &&
      other.lengthFt == lengthFt &&
      listEq(other.facets, facets) &&
      other.jumpFt == jumpFt;

  @override
  int get hashCode => Object.hash(id, type, a, b, lengthFt, Object.hashAll(facets), jumpFt);
}

class RoofHole {
  const RoofHole({required this.id, required this.kind, required this.polygon, required this.areaSqft});

  factory RoofHole.fromJson(Map<String, dynamic> j, String path) => RoofHole(
        id: asStr(j['id'], '$path.id'),
        kind: strOr(j, 'kind', path, 'hole'),
        polygon: asPoly(j['polygon'], '$path.polygon'),
        areaSqft: numOr(j, 'area_sqft', path, 0),
      );

  final String id, kind;
  final List<Pt> polygon;
  final double areaSqft;

  Map<String, dynamic> toJson() =>
      {'id': id, 'kind': kind, 'polygon': polyJson(polygon), 'area_sqft': areaSqft};
}

class RoofConfidence {
  const RoofConfidence({this.overall = 'unknown', this.notes = const []});

  factory RoofConfidence.fromJson(Map<String, dynamic> j, [String path = 'confidence']) => RoofConfidence(
        overall: strOr(j, 'overall', path, 'unknown'),
        notes: strList(j['notes'], '$path.notes'),
      );

  final String overall;
  final List<String> notes;

  Map<String, dynamic> toJson() => {'overall': overall, 'notes': notes};
}
