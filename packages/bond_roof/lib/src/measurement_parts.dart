import 'json_util.dart';
import 'model.dart';
import 'totals_variants.dart';

/// The service's verdict on a measurement (`verification.verdict`).
enum RoofVerdict {
  pass('pass'),
  adjusted('adjusted'),
  fail('fail'),
  unverified('unverified'),

  /// A verdict string this package does not know.
  unknown('unknown');

  const RoofVerdict(this.json);
  final String json;

  static RoofVerdict parse(Object? v) =>
      enumOrNull('$v', RoofVerdict.values, (e) => e.json) ?? RoofVerdict.unknown;
}

/// The fourteen `totals` of a 0.2 envelope, the four paired variants included.
class RoofEnvelopeTotals {
  const RoofEnvelopeTotals({
    required this.areaSqft,
    required this.squares,
    required this.eaveFt,
    required this.rakeFt,
    required this.ridgeFt,
    required this.hipFt,
    required this.valleyFt,
    required this.stepFlashingFt,
    required this.predominantPitch,
    required this.facets,
    required this.dripEdgeEaveFt,
    required this.dripEdgeEaveRakeFt,
    required this.ridgeCapRidgeFt,
    required this.ridgeCapRidgeHipFt,
  });

  /// The totals computed from [m], used for a bare 0.1 model and for any key an envelope omits.
  factory RoofEnvelopeTotals.fromModel(RoofModel m) {
    final t = m.totals;
    final v = RoofTotalsVariants.of(t);
    double len(EdgeType e) => t.lengthsFt[e] ?? 0.0;
    return RoofEnvelopeTotals(
      areaSqft: t.totalAreaSqft,
      squares: t.squares,
      eaveFt: len(EdgeType.eave),
      rakeFt: len(EdgeType.rake),
      ridgeFt: len(EdgeType.ridge),
      hipFt: len(EdgeType.hip),
      valleyFt: len(EdgeType.valley),
      stepFlashingFt: len(EdgeType.stepFlashing),
      predominantPitch: t.predominantPitchRise,
      facets: m.facets.length,
      dripEdgeEaveFt: v.dripEdgeEaveFt,
      dripEdgeEaveRakeFt: v.dripEdgeEaveRakeFt,
      ridgeCapRidgeFt: v.ridgeCapRidgeFt,
      ridgeCapRidgeHipFt: v.ridgeCapRidgeHipFt,
    );
  }

  /// Reads `totals`; a missing key falls back to the value computed from [m].
  factory RoofEnvelopeTotals.fromJson(Map<String, dynamic> j, RoofModel m, [String path = 'totals']) {
    final d = RoofEnvelopeTotals.fromModel(m);
    double n(String key, double fallback) => numOr(j, key, path, fallback);
    return RoofEnvelopeTotals(
      areaSqft: n('area_sqft', d.areaSqft),
      squares: n('squares', d.squares),
      eaveFt: n('eave_ft', d.eaveFt),
      rakeFt: n('rake_ft', d.rakeFt),
      ridgeFt: n('ridge_ft', d.ridgeFt),
      hipFt: n('hip_ft', d.hipFt),
      valleyFt: n('valley_ft', d.valleyFt),
      stepFlashingFt: n('step_flashing_ft', d.stepFlashingFt),
      predominantPitch: n('predominant_pitch', d.predominantPitch),
      facets: j['facets'] == null ? d.facets : asNum(j['facets'], '$path.facets').round(),
      dripEdgeEaveFt: n('drip_edge_eave_ft', d.dripEdgeEaveFt),
      dripEdgeEaveRakeFt: n('drip_edge_eave_rake_ft', d.dripEdgeEaveRakeFt),
      ridgeCapRidgeFt: n('ridge_cap_ridge_ft', d.ridgeCapRidgeFt),
      ridgeCapRidgeHipFt: n('ridge_cap_ridge_hip_ft', d.ridgeCapRidgeHipFt),
    );
  }

  final double areaSqft, squares, eaveFt, rakeFt, ridgeFt, hipFt, valleyFt, stepFlashingFt, predominantPitch;
  final int facets;
  final double dripEdgeEaveFt, dripEdgeEaveRakeFt, ridgeCapRidgeFt, ridgeCapRidgeHipFt;

  /// The paired variants as a [RoofTotalsVariants].
  RoofTotalsVariants get variants => RoofTotalsVariants(
        dripEdgeEaveFt: dripEdgeEaveFt,
        dripEdgeEaveRakeFt: dripEdgeEaveRakeFt,
        ridgeCapRidgeFt: ridgeCapRidgeFt,
        ridgeCapRidgeHipFt: ridgeCapRidgeHipFt,
      );

  Map<String, dynamic> toJson() => {
        'area_sqft': areaSqft,
        'squares': squares,
        'eave_ft': eaveFt,
        'rake_ft': rakeFt,
        'ridge_ft': ridgeFt,
        'hip_ft': hipFt,
        'valley_ft': valleyFt,
        'step_flashing_ft': stepFlashingFt,
        'predominant_pitch': predominantPitch,
        'facets': facets,
        'drip_edge_eave_ft': dripEdgeEaveFt,
        'drip_edge_eave_rake_ft': dripEdgeEaveRakeFt,
        'ridge_cap_ridge_ft': ridgeCapRidgeFt,
        'ridge_cap_ridge_hip_ft': ridgeCapRidgeHipFt,
      };
}

/// The `verification` block: what the verifier concluded and changed.
class RoofVerification {
  const RoofVerification({
    this.verdict = RoofVerdict.unverified,
    this.verdictRaw,
    this.notes = const [],
    this.adjustments = const [],
    this.originalTotals,
    this.modelId,
    this.rounds,
    this.usage,
    this.extra = const {},
  });

  factory RoofVerification.fromJson(Map<String, dynamic> j, [String path = 'verification']) {
    List<Map<String, dynamic>> adjustments() => j['adjustments'] == null
        ? const []
        : [
            for (final (i, a) in asList(j['adjustments'], '$path.adjustments').indexed)
              asMap(a, '$path.adjustments[$i]')
          ];
    return RoofVerification(
      verdict: RoofVerdict.parse(j['verdict']),
      verdictRaw: j['verdict'] is String ? j['verdict'] as String : null,
      notes: strList(j['notes'], '$path.notes'),
      adjustments: adjustments(),
      originalTotals: j['original_totals'] == null ? null : asMap(j['original_totals'], '$path.original_totals'),
      modelId: j['model'] is String ? j['model'] as String : null,
      rounds: j['rounds'] is num ? (j['rounds'] as num).round() : null,
      usage: j['usage'] == null ? null : asMap(j['usage'], '$path.usage'),
      extra: {
        for (final e in j.entries)
          if (!_known.contains(e.key)) e.key: e.value
      },
    );
  }

  static const _known = {'verdict', 'notes', 'adjustments', 'original_totals', 'model', 'rounds', 'usage'};

  final RoofVerdict verdict;

  /// The verdict string as received; kept when it is not one this package knows, and written back.
  final String? verdictRaw;
  final List<String> notes;

  /// Verifier operations, e.g. `{op: merge_collinear, edge_ids: [...], ...}`; kept as maps.
  final List<Map<String, dynamic>> adjustments;

  /// The totals before any verifier change (same keys as the envelope `totals`).
  final Map<String, dynamic>? originalTotals;

  /// The verifier's model id (wire key `model`).
  final String? modelId;
  final int? rounds;
  final Map<String, dynamic>? usage;
  final Map<String, dynamic> extra;

  Map<String, dynamic> toJson() => {
        'verdict': verdict == RoofVerdict.unknown && verdictRaw != null ? verdictRaw : verdict.json,
        'notes': notes,
        'adjustments': adjustments,
        if (originalTotals != null) 'original_totals': originalTotals,
        'model': modelId, // the service always sends the key, null when no model ran
        if (rounds != null) 'rounds': rounds,
        if (usage != null) 'usage': usage,
        ...extra,
      };
}
