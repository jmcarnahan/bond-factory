import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';

typedef Fixture = ({String name, Map<String, dynamic> json});

const _prefix = 'bond.roof_model/0.';

/// The hand-written 0.7 sample envelope (fixtures/roof_engine/roof_measurement_0.7_sample.json).
const samplePath = '../../fixtures/roof_engine/roof_measurement_0.7_sample.json';

/// A fresh copy of the raw sample envelope (safe to edit).
Map<String, dynamic> sampleJson() => jsonDecode(File(samplePath).readAsStringSync()) as Map<String, dynamic>;

RoofMeasurement loadSample() => RoofMeasurement.parseAny(sampleJson());

/// The generated 0.7 example (the real engine's output on a synthetic roof).
const enginePath = '../../fixtures/roof_engine/roof_measurement_0.7_engine.json';
Map<String, dynamic> engineJson() => jsonDecode(File(enginePath).readAsStringSync()) as Map<String, dynamic>;

/// The model of the sample.
RoofModel sampleModel() => loadSample().model;

/// Every model or envelope JSON in the repo-level fixtures/ folder (the old 0.2 envelopes and the closed-form models,
/// and the 0.4 engine example, kept for the Python side; not the 0.7 sample): the "old shapes" the reader must still open.
List<Fixture> loadOldFixtures() {
  final files = [
    for (final d in ['../../fixtures', '../../fixtures/roof_engine'])
      ...Directory(d).listSync().whereType<File>().where((f) => f.path.endsWith('.json') && !f.path.contains('_0.7_')),
  ]..sort((a, b) => a.path.compareTo(b.path));
  return [
    for (final f in files)
      if (_isRoof(jsonDecode(f.readAsStringSync())))
        (name: f.uri.pathSegments.last.replaceAll('.json', ''), json: jsonDecode(f.readAsStringSync()) as Map<String, dynamic>),
  ];
}

bool _isRoof(Object? j) =>
    j is Map &&
    ((j['schema'] is String && (j['schema'] as String).startsWith(_prefix)) ||
        (j['contract'] is String && (j['contract'] as String).startsWith('bond.roof_model/')));

/// What an envelope (or a bare model) holds that this package's reader does not know: every `totals` key (of the
/// envelope and of `model.totals`), every edge `type` and every object `kind`. Empty means the reader knows it all.
/// One line in a test: `expect(unknownEnvelopeKeys(json), isEmpty);`
List<String> unknownEnvelopeKeys(Map<String, dynamic> json) {
  final known = {...RoofEngineTotals.knownKeys, ...RoofTotals.ownKeys};
  final edgeTypes = {for (final t in EdgeType.values) t.json};
  final kinds = {for (final k in ObjectKind.values) k.json};
  final out = <String>[];
  void totals(Object? t, String path) {
    if (t is! Map) return;
    for (final k in t.keys) {
      if (!known.contains(k)) out.add('$path.$k');
    }
    final lengths = t['lengths_ft'];
    if (lengths is Map) {
      for (final k in lengths.keys) {
        if (k == 'parapet' && lengths[k] == 0) continue; // written as 0 by the engine
        if (!edgeTypes.contains(k)) out.add('$path.lengths_ft.$k');
      }
    }
  }

  final model = json['model'] is Map ? json['model'] as Map : json;
  totals(json['totals'], 'totals');
  if (!identical(model, json)) totals(model['totals'], 'model.totals');
  for (final (i, e) in ((model['edges'] as List?) ?? const []).indexed) {
    if (e is Map && !edgeTypes.contains(e['type'])) out.add('model.edges[$i].type=${e['type']}');
  }
  for (final (i, o) in ((model['objects'] as List?) ?? const []).indexed) {
    if (o is Map && !kinds.contains(o['kind'])) out.add('model.objects[$i].kind=${o['kind']}');
  }
  return out;
}

/// The texts of a scene, in drawing order.
List<String> textsOf(Scene s) => [for (final p in s.prims) if (p is TextPrim) p.text];
