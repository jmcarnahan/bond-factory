import 'dart:math' as math;

import 'json_util.dart';

export 'json_util.dart' show Pt;

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
class RoofBlock {
  const RoofBlock({
    required this.id,
    required this.form,
    required this.polygon,
    this.pitchRise = 0,
    this.gableEdges = const [],
    this.extra = const {},
  });

  factory RoofBlock.fromJson(Map<String, dynamic> j, String path, [List<String>? notes]) {
    final formText = asStr(j['form'], '$path.form');
    var form = enumOrNull(formText, BlockForm.values, (v) => v.json);
    if (form == null) {
      form = BlockForm.flat;
      notes?.add('$path.form: unknown value "$formText", read as flat');
    }
    return RoofBlock(
      id: asStr(j['id'], '$path.id'),
      form: form,
      polygon: asPoly(j['polygon'], '$path.polygon'),
      pitchRise: numOr(j, 'pitch_rise', path, 0),
      gableEdges: j['gable_edges'] == null
          ? const []
          : [
              for (final (i, v) in asList(j['gable_edges'], '$path.gable_edges').indexed)
                asNum(v, '$path.gable_edges[$i]').toInt()
            ],
      extra: {
        for (final e in j.entries)
          if (!_blockKnown.contains(e.key)) e.key: e.value
      },
    );
  }

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
        'polygon': polyJson(polygon),
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

  factory RoofFacet.fromJson(Map<String, dynamic> j, String path, [List<String>? notes]) {
    final area = asNum(j['area_sqft'], '$path.area_sqft');
    final pitch = numOr(j, 'pitch_rise', path, 0);
    final kindText = asStr(j['kind'], '$path.kind');
    var kind = enumOrNull(kindText, FacetKind.values, (v) => v.json);
    if (kind == null) {
      kind = pitch > 0 ? FacetKind.sloped : FacetKind.flat;
      notes?.add('$path.kind: unknown value "$kindText", read as ${kind.json} from the pitch');
    }
    return RoofFacet(
      id: asStr(j['id'], '$path.id'),
      block: strOr(j, 'block', path, ''),
      kind: kind,
      polygon: asPoly(j['polygon'], '$path.polygon'),
      pitchRise: pitch,
      aspectDeg: numOrNull(j, 'aspect_deg', path),
      planAreaSqft: numOr(j, 'plan_area_sqft', path, area),
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
        'polygon': polyJson(polygon),
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
        'points': [ptJson(a), ptJson(b)],
        'length_ft': lengthFt,
        'facets': facets,
      };
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
