import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';

/// Every model fixture: this package's test/fixtures plus the repo-level fixtures/ folder.
/// Files whose schema is not `bond.roof_model/0.x` (blocks, solar fixtures) are skipped.
List<({String name, Map<String, dynamic> json})> loadFixtures() {
  final out = <({String name, Map<String, dynamic> json})>[];
  for (final dirPath in ['test/fixtures', '../../fixtures']) {
    final dir = Directory(dirPath);
    if (!dir.existsSync()) continue;
    final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    for (final f in files) {
      final j = jsonDecode(f.readAsStringSync());
      if (j is Map<String, dynamic> && j['schema'] == 'bond.roof_model/0.1') {
        out.add((name: f.uri.pathSegments.last.replaceAll('.json', ''), json: j));
      }
    }
  }
  return out;
}

List<RoofModel> loadModels() => [for (final f in loadFixtures()) RoofModel.fromJson(f.json)];
