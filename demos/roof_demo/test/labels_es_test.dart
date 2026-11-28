import 'package:bond_roof/bond_roof.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roof_demo/src/labels_es.dart';

void main() {
  test('the Spanish sample has a value for every RoofLabels key and no extras', () {
    expect(roofLabelsEs.keys.toSet(), RoofLabels.keys.toSet());
    expect(roofLabelsEs.values.every((v) => v.isNotEmpty), isTrue);
  });

  test('roofing terms are used', () {
    final l = RoofLabels.fromMap(roofLabelsEs);
    expect(l.legendEave, contains('Alero'));
    expect(l.legendRidge, contains('Cumbrera'));
    expect(l.legendHip, 'Limas tesas');
    expect(l.legendValley, 'Limas hoyas');
    expect(l.legendStepFlashing, 'Tapajuntas de pared lateral');
    expect(l.legendWallFlashing, 'Tapajuntas de pared frontal');
    expect(l.legendChimney, 'Chimenea');
    expect(l.legendTransition, contains('Transici'));
    expect(l.legendUnspecified, 'Sin especificar');
  });
}
