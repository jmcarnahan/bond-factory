import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';

typedef Fixture = ({String name, Map<String, dynamic> json});

const _prefix = 'bond.roof_model/0.';

Iterable<({String name, Map<String, dynamic> json})> _jsonFiles() sync* {
  for (final dirPath in ['test/fixtures', '../../fixtures']) {
    final dir = Directory(dirPath);
    if (!dir.existsSync()) continue;
    final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    for (final f in files) {
      final j = jsonDecode(f.readAsStringSync());
      if (j is Map<String, dynamic>) yield (name: f.uri.pathSegments.last.replaceAll('.json', ''), json: j);
    }
  }
}

/// Every model fixture: this package's test/fixtures plus the repo-level fixtures/ folder.
/// A bare model (`schema` starts with `bond.roof_model/0.`) is returned as is; for a 0.2
/// envelope (loaded through [RoofMeasurement.parseAny]) the embedded model is returned. Other
/// files (blocks, solar responses) are skipped.
List<Fixture> loadFixtures() {
  final out = <Fixture>[];
  for (final f in _jsonFiles()) {
    final schema = f.json['schema'], contract = f.json['contract'];
    if (schema is String && schema.startsWith(_prefix)) {
      out.add(f);
    } else if (contract is String && contract.startsWith('bond.roof_model/')) {
      out.add((name: f.name, json: RoofMeasurement.parseAny(f.json).model.toJson()));
    }
  }
  return out;
}

List<RoofModel> loadModels() => [for (final f in loadFixtures()) RoofModel.fromJson(f.json)];

/// Every 0.2 envelope fixture, raw and parsed.
List<({String name, Map<String, dynamic> json, RoofMeasurement measurement})> loadEnvelopes() => [
      for (final f in _jsonFiles())
        if (f.json['contract'] is String && (f.json['contract'] as String).startsWith('bond.roof_model/'))
          (name: f.name, json: f.json, measurement: RoofMeasurement.parseAny(f.json)),
    ];

/// Every bare 0.x model file (no envelope), raw.
List<Fixture> loadBareModels() => [
      for (final f in _jsonFiles())
        if (f.json['schema'] is String && (f.json['schema'] as String).startsWith(_prefix)) f,
    ];
