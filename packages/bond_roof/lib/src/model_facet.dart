import 'json_util.dart';

enum FacetKind {
  flat('flat'),
  sloped('sloped');

  const FacetKind(this.json);
  final String json;
}

class RoofFacet {
  const RoofFacet({
    required this.id,
    required this.kind,
    required this.polygon,
    required this.pitchRise,
    this.aspectDeg,
    required this.planAreaSqft,
    required this.areaSqft,
    this.roofType,
    this.pitchFit,
    this.pitchSigma,
    this.borderline,
    this.supportedPct,
    this.points,
    this.rmsFt,
    this.planEq,
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
    final planEq = j['plane_eq'];
    return RoofFacet(
      id: asStr(j['id'], '$path.id'),
      kind: kind,
      polygon: asPoly(j['polygon'], '$path.polygon'),
      pitchRise: pitch,
      aspectDeg: numOrNull(j, 'aspect_deg', path),
      planAreaSqft: numOr(j, 'plan_area_sqft', path, area),
      areaSqft: area,
      roofType: j['roof_type'] is String ? j['roof_type'] as String : null,
      pitchFit: numOrNull(j, 'pitch_fit', path),
      pitchSigma: numOrNull(j, 'pitch_sigma', path),
      borderline: j['borderline'] is bool ? j['borderline'] as bool : null,
      supportedPct: numOrNull(j, 'supported_pct', path),
      points: numOrNull(j, 'points', path)?.round(),
      rmsFt: numOrNull(j, 'rms_ft', path),
      planEq: planEq == null
          ? null
          : [for (final (i, v) in asList(planEq, '$path.plane_eq').indexed) asNum(v, '$path.plane_eq[$i]')],
    );
  }

  final String id;
  final FacetKind kind;
  final List<Pt> polygon;
  final double pitchRise;
  final double? aspectDeg;
  final double planAreaSqft, areaSqft;

  /// `flat` or `pitched` (cut at 2.0/12), envelope 0.4. Null for an older envelope, and a value
  /// this package does not know is kept as is: only `flat` changes how a facet is drawn.
  final String? roofType;

  /// Fitted pitch (rise per 12) and its standard error; envelope 0.4.
  final double? pitchFit, pitchSigma;

  /// True when the fitted pitch straddles 2.0/12 (the salesperson should confirm); envelope 0.4.
  final bool? borderline;

  /// Share of the facet backed by roof points, in percent; envelope 0.4.
  final double? supportedPct;

  /// Number of roof points on the facet; envelope 0.4.
  final int? points;

  /// Plane fit residual, feet; envelope 0.4.
  final double? rmsFt;

  /// The plane `z = a x + b y + c` as `[a, b, c]` (feet above ground, plan feet); envelope 0.4.
  final List<double>? planEq;

  /// True for a facet the engine typed `flat` (drawn hatched). False when [roofType] is absent.
  bool get isFlatRoofType => roofType == 'flat';

  /// True for a facet flagged "low slope, confirm". False when [borderline] is absent.
  bool get isBorderline => borderline == true;

  Map<String, dynamic> toJson() => {
        'id': id,
        'kind': kind.json,
        'polygon': polyJson(polygon),
        'pitch_rise': pitchRise,
        'aspect_deg': aspectDeg,
        'plan_area_sqft': planAreaSqft,
        'area_sqft': areaSqft,
        if (roofType != null) 'roof_type': roofType,
        if (pitchFit != null) 'pitch_fit': pitchFit,
        if (pitchSigma != null) 'pitch_sigma': pitchSigma,
        if (borderline != null) 'borderline': borderline,
        if (supportedPct != null) 'supported_pct': supportedPct,
        if (points != null) 'points': points,
        if (rmsFt != null) 'rms_ft': rmsFt,
        if (planEq != null) 'plane_eq': planEq,
      };

  @override
  bool operator ==(Object other) =>
      other is RoofFacet &&
      other.id == id &&
      other.kind == kind &&
      listEq(other.polygon, polygon) &&
      other.pitchRise == pitchRise &&
      other.aspectDeg == aspectDeg &&
      other.planAreaSqft == planAreaSqft &&
      other.areaSqft == areaSqft &&
      other.roofType == roofType &&
      other.pitchFit == pitchFit &&
      other.pitchSigma == pitchSigma &&
      other.borderline == borderline &&
      other.supportedPct == supportedPct &&
      other.points == points &&
      other.rmsFt == rmsFt &&
      listEq(other.planEq, planEq);

  @override
  int get hashCode => Object.hash(id, kind, Object.hashAll(polygon), pitchRise, aspectDeg, planAreaSqft,
      areaSqft, roofType, pitchFit, pitchSigma, borderline, supportedPct, points, rmsFt,
      planEq == null ? null : Object.hashAll(planEq!));
}

