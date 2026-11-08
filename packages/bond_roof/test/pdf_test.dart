import 'dart:convert';

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/roof_pdf.dart';
import 'package:test/test.dart';

import 'support.dart';

void main() {
  test('scenesToPdf returns a PDF with one page per scene', () async {
    final m = loadModels().first;
    final bytes = await scenesToPdf(
      [LengthDiagram.build(m), AreaDiagram.build(m), SummaryBlock.build(m)],
      title: 'Test report',
    );
    expect(ascii.decode(bytes.sublist(0, 5)), '%PDF-');
    expect(bytes.length, greaterThan(2000));
    final text = latin1.decode(bytes);
    expect(RegExp(r'/Type\s*/Page(?![s\w])').allMatches(text).length, 3);
    expect(text, contains('%%EOF'));
  });

  test('non-Latin-1 text does not crash without a font', () async {
    final json = Map.of(loadFixtures().first.json);
    json['address'] = {'formatted': 'Calle Ñandú 12 – 中文'};
    final m = RoofModel.fromJson(json);
    final bytes = await scenesToPdf([LengthDiagram.build(m)]);
    expect(ascii.decode(bytes.sublist(0, 4)), '%PDF');
  });

  test('no scenes is an ArgumentError', () {
    expect(scenesToPdf([]), throwsArgumentError);
  });
}
