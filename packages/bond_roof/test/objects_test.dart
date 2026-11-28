import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

import 'scene_checks.dart';
import 'support.dart';

const _style = DiagramStyle.report;

/// The plan marks of one kind: outlined white rectangles drawn 2 px wide (the legend swatch is 1.5 px).
List<PolyPrim> _planMarks(Scene s, ObjectKind k) => [
      for (final p in s.prims)
        if (p is PolyPrim && p.stroke == _style.objectColorOf(k) && p.fill == _style.objectFill && p.width >= 1.9) p
    ];

({double l, double t, double r, double b}) _box(List<Pt> pts) => (
      l: pts.map((p) => p.x).reduce((a, b) => a < b ? a : b),
      t: pts.map((p) => p.y).reduce((a, b) => a < b ? a : b),
      r: pts.map((p) => p.x).reduce((a, b) => a > b ? a : b),
      b: pts.map((p) => p.y).reduce((a, b) => a > b ? a : b),
    );

RoofModel _withObjects(List<Map<String, Object?>> objects) {
  final j = sampleJson()['model'] as Map<String, dynamic>;
  j['objects'] = objects;
  (j['totals'] as Map).remove('chimney_count');
  (j['totals'] as Map).remove('lantern_count');
  return RoofModel.fromJson(j);
}

void main() {
  final m = sampleModel();

  for (final layout in ReportLayout.values) {
    group('${layout.name} layout', () {
      final len = LengthDiagram.build(m, layout: layout);
      final area = AreaDiagram.build(m, layout: layout);

      test('each chimney and lantern is one outlined rectangle on the length diagram and on the area diagram', () {
        for (final s in [len, area]) {
          expect(_planMarks(s, ObjectKind.chimney), hasLength(1), reason: s.title);
          expect(_planMarks(s, ObjectKind.lantern), hasLength(1), reason: s.title);
          expectFits(s);
        }
      });

      test('with its one-letter mark, taken from the labels', () {
        for (final s in [len, area]) {
          final t = textsOf(s);
          expect(t.where((x) => x == 'C'), isNotEmpty, reason: s.title);
          expect(t.where((x) => x == 'L'), isNotEmpty, reason: s.title);
        }
        final es = RoofLabels.fromMap({'mark_chimney': 'Ch', 'mark_lantern': 'Tr'});
        final t = textsOf(AreaDiagram.build(m, labels: es, layout: layout));
        expect(t, containsAll(['Ch', 'Tr']));
        expect(t, isNot(contains('C')));
      });

      test('the mark letter is readable', () {
        final letters = area.prims.whereType<TextPrim>().where((p) => p.text == 'C' || p.text == 'L');
        for (final p in letters) {
          expect(p.size, greaterThanOrEqualTo(layout == ReportLayout.compact ? 13.5 : 10));
          expect(p.bold, isTrue);
        }
      });

      test('they are never a facet: same facet regions, same totals, no region for an object', () {
        expect(area.regions.map((r) => r.id), m.facets.map((f) => f.id));
        expect(len.regions.map((r) => r.id), m.facets.map((f) => f.id));
        final without = _withObjects([]);
        expect(RoofFigures.of(m).areaSqft, RoofFigures.of(without).areaSqft);
        expect(AreaDiagram.build(without, layout: layout).regions.length, area.regions.length);
      });

      test('no facet label sits on a mark', () {
        final marks = [..._planMarks(area, ObjectKind.chimney), ..._planMarks(area, ObjectKind.lantern)].map((p) => _box(p.pts));
        final facetLabels = area.prims.whereType<TextPrim>().where((p) => RegExp(r'^(\d+/12|Flat|[\d,]+)').hasMatch(p.text));
        for (final p in facetLabels) {
          for (final b in marks) {
            final inside = p.at.x > b.l && p.at.x < b.r && p.at.y > b.t && p.at.y < b.b;
            expect(inside, isFalse, reason: 'label "${p.text}" at ${p.at}');
          }
        }
      });
    });
  }

  test('the lantern (no polygon) is its size in feet at the plan scale, centred on the object', () {
    final area = AreaDiagram.build(m);
    final f1 = _box(area.regions.firstWhere((r) => r.id == 'f1').pts);
    final f1Model = m.facets.firstWhere((f) => f.id == 'f1').polygon;
    final spanX = f1Model.map((p) => p.x).reduce((a, b) => a > b ? a : b) - f1Model.map((p) => p.x).reduce((a, b) => a < b ? a : b);
    final scale = (f1.r - f1.l) / spanX;
    final lantern = _box(_planMarks(area, ObjectKind.lantern).single.pts);
    expect(lantern.r - lantern.l, closeTo(5 * scale, 1e-6));
    expect(lantern.b - lantern.t, closeTo(5 * scale, 1e-6));
  });

  test('a chimney with a polygon is drawn as that polygon: its corners are the polygon points times the scale', () {
    final c = m.objects.firstWhere((o) => o.kind == ObjectKind.chimney);
    expect(c.polygon, hasLength(4));
    expect(c.returns, 41);
    for (final layout in ReportLayout.values) {
      final area = AreaDiagram.build(m, layout: layout);
      final r = area.regions.firstWhere((r) => r.id == 'f1').pts;
      final f1 = _box(r);
      final model = m.facets.firstWhere((f) => f.id == 'f1').polygon;
      final minX = model.map((p) => p.x).reduce((a, b) => a < b ? a : b);
      final maxX = model.map((p) => p.x).reduce((a, b) => a > b ? a : b);
      final scale = (f1.r - f1.l) / (maxX - minX);
      final drawn = _planMarks(area, ObjectKind.chimney).single.pts;
      expect(drawn, hasLength(4));
      for (final (i, p) in c.polygon!.indexed) {
        expect(drawn[i].x, closeTo(f1.l + (p.x - minX) * scale, 1e-6));
        expect(drawn[i].y, closeTo(f1.b - p.y * scale, 1e-6));
      }
      // Rotated: not an axis-aligned rectangle.
      expect(drawn[0].y, isNot(closeTo(drawn[1].y, 0.5)));
    }
  });

  test('polygon round-trips through the model', () {
    final c = m.objects.firstWhere((o) => o.kind == ObjectKind.chimney);
    expect(RoofObject.fromJson(c.toJson(), 'o').polygon, c.polygon);
    expect(m.objects.firstWhere((o) => o.kind == ObjectKind.lantern).polygon, isNull);
  });

  test('a small polygon is scaled about its centre to the minimum side', () {
    final tiny = _withObjects([
      {'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [0.2, 0.2], 'polygon': [[19.9, 5.9], [20.1, 5.9], [20.1, 6.1], [19.9, 6.1]]},
    ]);
    final pts = _planMarks(AreaDiagram.build(tiny, layout: ReportLayout.compact), ObjectKind.chimney).single.pts;
    final b = _box(pts);
    expect(b.r - b.l, closeTo(18, 1e-6));
    expect((b.l + b.r) / 2, closeTo((pts[0].x + pts[2].x) / 2, 1e-6));
  });

  test('a mark is never smaller than the smallest readable side', () {
    final tiny = _withObjects([
      {'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [0.2, 0.2]},
    ]);
    final b = _box(_planMarks(AreaDiagram.build(tiny, layout: ReportLayout.compact), ObjectKind.chimney).single.pts);
    expect(b.r - b.l, greaterThanOrEqualTo(18));
    expect(b.b - b.t, greaterThanOrEqualTo(18));
  });

  group('legend rows and totals row, only when present', () {
    test('both present: "Chimney" and "Roof lantern" rows with their counts, "Chimneys" in the totals', () {
      final t = textsOf(LengthDiagram.build(m));
      expect(t, containsAll(['Chimney', 'Roof lantern']));
      expect(totalRows(m, const RoofLabels()).firstWhere((r) => r.id == 'chimneys').value, '1');
    });

    test('only a chimney: no lantern row', () {
      final one = _withObjects([
        {'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [3.0, 3.0]},
        {'id': 'p', 'kind': 'chimney', 'center': [10.0, 6.0], 'size_ft': [3.0, 3.0]},
      ]);
      final t = textsOf(LengthDiagram.build(one));
      expect(t, contains('Chimney'));
      expect(t, isNot(contains('Roof lantern')));
      expect(totalRows(one, const RoofLabels()).firstWhere((r) => r.id == 'chimneys').value, '2');
      expect(_planMarks(LengthDiagram.build(one), ObjectKind.chimney), hasLength(2));
    });

    test('an unknown object is kept in the model, never drawn, never listed', () {
      final u = _withObjects([
        {'id': 'o', 'kind': 'unknown', 'center': [20.0, 6.0], 'size_ft': [3.0, 3.0]},
      ]);
      expect(u.objects, hasLength(1));
      for (final s in [LengthDiagram.build(u), AreaDiagram.build(u)]) {
        expect(_planMarks(s, ObjectKind.chimney), isEmpty);
        expect(_planMarks(s, ObjectKind.lantern), isEmpty);
        expect(textsOf(s), isNot(contains('Chimney')));
      }
      expect(totalRows(u, const RoofLabels()).where((r) => r.id == 'chimneys'), isEmpty);
    });

    test('an envelope without objects draws exactly as it does today: no object prim, no legend row, no count', () {
      final none = _withObjects([]);
      for (final s in [LengthDiagram.build(none), AreaDiagram.build(none), SummaryBlock.build(none)]) {
        expect(s.prims.whereType<PolyPrim>().where((p) => _style.objectColors.values.contains(p.stroke)), isEmpty, reason: s.title);
        final t = textsOf(s);
        expect(t, isNot(contains('C')));
        expect(t, isNot(contains('L')));
        expect(t, isNot(contains('Chimney')));
        expect(t, isNot(contains('Chimneys')));
        expect(t, isNot(contains('Roof lantern')));
      }
      // And the same envelope with the key absent is the same drawing.
      final j = sampleJson()['model'] as Map<String, dynamic>..remove('objects');
      (j['totals'] as Map)
        ..remove('chimney_count')
        ..remove('lantern_count');
      final absent = RoofModel.fromJson(j);
      expect(sceneToSvg(LengthDiagram.build(absent)), sceneToSvg(LengthDiagram.build(none)));
      expect(sceneToSvg(AreaDiagram.build(absent)), sceneToSvg(AreaDiagram.build(none)));
    });
  });

  group('a mark can never blow up or leave the page', () {
    void expectSane(RoofModel model, {int marks = 1}) {
      for (final layout in ReportLayout.values) {
        for (final s in [LengthDiagram.build(model, layout: layout), AreaDiagram.build(model, layout: layout)]) {
          expectFits(s);
          expect(_planMarks(s, ObjectKind.chimney), hasLength(marks), reason: '${s.title} ${layout.name}');
        }
      }
    }

    test('a 0.1 x 8 ft sliver is stretched on its short axis only', () {
      expectSane(_withObjects([{'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [0.1, 8.0]}]));
      final b = _box(_planMarks(AreaDiagram.build(_withObjects([{'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [0.1, 8.0]}])), ObjectKind.chimney).single.pts);
      expect(b.r - b.l, closeTo(18, 1e-6));
      expect(b.b - b.t, greaterThan(100));
    });

    test('a 0.1 x 30 ft sliver stays finite and bounded', () {
      final j = _withObjects([{'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [0.1, 30.0]}]);
      for (final p in _planMarks(AreaDiagram.build(j), ObjectKind.chimney).single.pts) {
        expect(p.x.abs() < 5000 && p.y.abs() < 5000, isTrue);
      }
    });

    test('zero size, and polygons of identical points, are skipped', () {
      expectSane(_withObjects([{'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [0.0, 0.0]}]), marks: 0);
      expectSane(_withObjects([{'id': 'o', 'kind': 'chimney', 'center': [20.0, 6.0], 'size_ft': [1.0, 1.0],
        'polygon': [[20.0, 6.0], [20.0, 6.0], [20.0, 6.0]]}]), marks: 0);
    });

    test('an object off the roof is not drawn, nor listed in the legend rows of marks', () {
      expectSane(_withObjects([{'id': 'o', 'kind': 'chimney', 'center': [500.0, 500.0], 'size_ft': [3.0, 3.0]}]), marks: 0);
    });

    test('a model with objects and no geometry draws no mark and no huge coordinate', () {
      const model = RoofModel(
        totals: const RoofTotals(totalAreaSqft: 0, pitchedAreaSqft: 0, flatAreaSqft: 0, squares: 0, lengthsFt: {}),
        objects: const [RoofObject(id: 'o', kind: ObjectKind.chimney, center: (x: 3.0, y: 3.0), sizeFt: (3.0, 3.0))],
      );
      expectSane(model, marks: 0);
    });
  });

  test('marks survive the SVG export', () {
    final svg = sceneToSvg(AreaDiagram.build(m));
    expect(svg, contains('>C<'));
    expect(svg, contains('>L<'));
  });
}
