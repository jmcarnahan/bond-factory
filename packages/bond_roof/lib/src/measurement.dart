import 'json_util.dart';
import 'model.dart';

/// A `bond.roof_model/0.x` envelope: the model plus the service's totals, confidence and warnings. Use [parseAny] when
/// the input may be a bare model. An old envelope's `verification` block and any other key this package no longer
/// models stay in [extra] and are written back.
class RoofMeasurement {
  const RoofMeasurement({
    this.contract = 'bond.roof_model/0.6',
    this.pipelineVersion = 'unknown',
    required this.methodUsed,
    required this.footprintSource,
    this.generatedAt,
    required this.model,
    this.totals = const RoofEngineTotals(),
    required this.confidenceScore,
    this.warnings = const [],
    this.warningCodes = const [],
    this.extra = const {},
  });

  /// Wraps a bare model: method from `source.method`, footprint source mapped from `source.footprint.provider`,
  /// confidence from `confidence.overall`, totals from the model's own 0.6 keys (none when it has none).
  factory RoofMeasurement.fromModel(RoofModel m) {
    final gen = m.extra['generated_at'];
    return RoofMeasurement(
      methodUsed: m.source.method,
      footprintSource: _footprintSource(m.source.raw['footprint']),
      generatedAt: gen is String ? DateTime.tryParse(gen) : null,
      model: m,
      totals: m.totals.engine ?? const RoofEngineTotals(),
      confidenceScore: _scoreOf(m.confidence.overall),
      warnings: m.warnings,
    );
  }

  /// Parses an envelope. Missing optional keys are tolerated (totals fall back to the model's own 0.6 keys, or are
  /// empty); unknown top-level keys are kept in [extra].
  factory RoofMeasurement.fromJson(Map<String, dynamic> json) {
    final contract = asStr(json['contract'], 'contract');
    if (!contract.startsWith(_supported)) badJson('contract', 'unsupported contract "$contract"');
    final model = RoofModel.fromJson(asMap(json['model'], 'model'));
    final gen = json['generated_at'];
    return RoofMeasurement(
      contract: contract,
      pipelineVersion: strOr(json, 'pipeline_version', '', 'unknown'),
      methodUsed: json['method_used'] is String ? json['method_used'] as String : model.source.method,
      footprintSource: json['footprint_source'] is String
          ? json['footprint_source'] as String
          : _footprintSource(model.source.raw['footprint']),
      generatedAt: gen is String ? DateTime.tryParse(gen) : null,
      model: model,
      totals: (json['totals'] == null ? null : RoofEngineTotals.fromJson(asMap(json['totals'], 'totals'))) ??
          model.totals.engine ??
          const RoofEngineTotals(),
      confidenceScore: json['confidence'] == null
          ? _scoreOf(model.confidence.overall)
          : asNum(json['confidence'], 'confidence').clamp(0.0, 1.0),
      warnings: strList(json['warnings'], 'warnings'),
      warningCodes: strList(json['warning_codes'], 'warning_codes'),
      extra: {
        for (final e in json.entries)
          if (!_known.contains(e.key)) e.key: e.value
      },
    );
  }

  /// An envelope (`contract` starts with `bond.roof_model/`) is read as is; a bare model
  /// (`schema` starts with `bond.roof_model/`) is wrapped by [RoofMeasurement.fromModel].
  /// Anything else throws a [FormatException].
  static RoofMeasurement parseAny(Map<String, dynamic> json) {
    final contract = json['contract'];
    if (contract is String && contract.startsWith(_contractPrefix)) return RoofMeasurement.fromJson(json);
    final schema = json['schema'];
    if (schema is String && schema.startsWith(_contractPrefix)) {
      return RoofMeasurement.fromModel(RoofModel.fromJson(json));
    }
    badJson('contract', 'expected a bond.roof_model envelope or model');
  }

  static const _contractPrefix = 'bond.roof_model/';
  static const _supported = 'bond.roof_model/0.';
  static const _known = {
    'contract', 'pipeline_version', 'method_used', 'footprint_source', 'generated_at', 'model', 'totals',
    'confidence', 'warnings', 'warning_codes',
  };

  final String contract, pipelineVersion;

  /// `lidar_skeleton`, `planes` or whatever a newer service reports.
  final String methodUsed;

  /// `lariac`, `osm`, `lidar_hull` or `unknown`.
  final String footprintSource;

  /// Null when the envelope has no parseable `generated_at`.
  final DateTime? generatedAt;
  final RoofModel model;
  /// The envelope `totals` (every field nullable: a key the service did not send is not available).
  final RoofEngineTotals totals;

  /// 0..1; the envelope key is `confidence`.
  final double confidenceScore;
  final List<String> warnings;

  /// One code per warning when the service sends them (see the contract's closed list); kept as
  /// strings so unknown codes survive.
  final List<String> warningCodes;

  /// Top-level keys this package does not model.
  final Map<String, dynamic> extra;

  Map<String, dynamic> toJson() => {
        'contract': contract,
        'pipeline_version': pipelineVersion,
        'method_used': methodUsed,
        'footprint_source': footprintSource,
        if (generatedAt != null)
          'generated_at': generatedAt!.toUtc().toIso8601String().replaceFirst(RegExp(r'\.0+Z$'), 'Z'),
        'model': model.toJson(),
        'totals': totals.toJson(),
        'confidence': confidenceScore,
        'warnings': warnings,
        'warning_codes': warningCodes,
        ...extra,
      };
}

double _scoreOf(String overall) => switch (overall) {
      'high' => 0.9,
      'medium' => 0.7,
      _ => 0.5,
    };

String _footprintSource(Object? footprint) {
  final p = footprint is Map && footprint['provider'] is String ? (footprint['provider'] as String).toLowerCase() : '';
  if (p.contains('lariac') || p.startsWith('la_county') || p.startsWith('lacounty')) return 'lariac';
  if (p == 'osm' || p.startsWith('osm') || p.contains('overpass')) return 'osm';
  if (p.startsWith('lidar')) return 'lidar_hull';
  return 'unknown';
}
