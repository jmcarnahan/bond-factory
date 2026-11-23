import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'support.dart';

/// FNV-1a, 63 bits: a stable fingerprint for the golden file (not a security hash).
String _h(String s) {
  var x = 0xcbf29ce484222325 & 0x7fffffffffffffff;
  for (final c in s.codeUnits) {
    x = ((x ^ c) * 0x100000001b3) & 0x7fffffffffffffff;
  }
  return x.toRadixString(16);
}

/// Pins "old envelopes draw and write back exactly as before envelope 0.4": the SVG of the length, area and
/// summary scenes (both layouts) and the `toJson` of every shipped 0.1-0.3 fixture, against a golden made from
/// the commit before the 0.4 work. If a fixture changes on purpose, regenerate the golden and say why.
void main() {
  test('every old fixture scene and toJson matches the golden digests', () {
    final got = StringBuffer();
    for (final f in loadFixtures()) {
      final m = RoofModel.fromJson(f.json);
      for (final l in ReportLayout.values) {
        got.writeln('${f.name} $l len ${_h(sceneToSvg(LengthDiagram.build(m, layout: l)))} '
            'area ${_h(sceneToSvg(AreaDiagram.build(m, layout: l)))} sum ${_h(sceneToSvg(SummaryBlock.build(m, layout: l)))}');
      }
      got.writeln('${f.name} json ${_h(jsonEncode(m.toJson()))}');
    }
    for (final e in loadEnvelopes()) {
      got.writeln('${e.name} env ${_h(jsonEncode(e.measurement.toJson()))}');
    }
    final want = File('test/golden/old_fixture_digests.txt').readAsStringSync();
    expect(got.toString().split('\n'), want.split('\n'));
  });
}
