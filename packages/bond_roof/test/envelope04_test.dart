import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/src/hatch.dart';
import 'package:bond_roof/src/polylabel.dart' show pointInPolygon;
import 'package:test/test.dart';

import 'scene_checks.dart';
import 'support.dart';

/// Envelope 0.4 (synthetic example in test/envelope04/, no real address or geometry).
Map<String, dynamic> _json() =>
    jsonDecode(File('test/envelope04/synthetic_mixed_0.4.json').readAsStringSync()) as Map<String, dynamic>;

Map<String, dynamic> _viaText(Map<String, dynamic> j) => jsonDecode(jsonEncode(j)) as Map<String, dynamic>;

List<LinePrim> _hatch(Scene s) =>
    [for (final p in s.prims) if (p is LinePrim && p.color == DiagramStyle.report.hatchColor) p];

List<PolyPrim> _borderlineOutlines(Scene s) =>
    [for (final p in s.prims) if (p is PolyPrim && p.stroke == DiagramStyle.report.borderlineStroke) p];

List<String> _texts(Scene s) => [for (final p in s.prims) if (p is TextPrim) p.text];

/// The REAL shipped example written by the service (fixtures/roof_engine/), read from the repo at test time.
Map<String, dynamic> _real() =>
    jsonDecode(File('../../fixtures/roof_engine/roof_measurement_0.4_engine.json').readAsStringSync()) as Map<String, dynamic>;

void main() {
  group('the shipped engine example (fixtures/roof_engine)', () {
    final j = _real();
    final r = RoofMeasurement.parseAny(j);

    test('parses with no parse notes and keeps every 0.4 field', () {
      expect(r.model.parseNotes, isEmpty);
      expect(r.model.facets, isNotEmpty);
      for (final f in r.model.facets) {
        expect(f.roofType, isNotNull);
        expect(f.pitchFit, isNotNull);
        expect(f.planEq, hasLength(3));
        expect(f.borderline, isNotNull);
      }
      expect(r.model.quality!.engine, 'planes/1');
      expect(r.model.quality!.verdict, isNotNull);
      expect(r.model.building!.outlineId, isNotNull);
      final e = r.totals.engine!;
      expect(e.hasRoofing, isTrue);
      expect(e.complexity!.hint, isNotNull);
      expect(e.roofingPitchedSqft! + e.roofingFlatSqft!, closeTo(e.planesSurfaceAreaSqft!, 0.1));
      expect(r.model.edges.map((x) => x.type).toSet(), containsAll([EdgeType.flatEdge, EdgeType.levelChange]));
      expect(r.model.edges.where((x) => x.type == EdgeType.levelChange).every((x) => x.jumpFt != null), isTrue);
    });

    test('round-trips: facets, edges, quality, source and envelope totals', () {
      final back = _viaText(r.toJson());
      expect(back['model']['facets'], j['model']['facets']);
      expect(back['model']['edges'], j['model']['edges']);
      expect(back['model']['quality'], j['model']['quality']);
      expect(back['model']['source'], j['model']['source']);
      for (final k in (j['totals'] as Map).keys.where((k) => k != 'plane_count')) {
        expect(back['totals'][k], j['totals'][k], reason: k);
      }
    });

    for (final layout in ReportLayout.values) {
      test('diagrams build and fit ($layout), hatch present', () {
        for (final s in [AreaDiagram.build(r.model, layout: layout), LengthDiagram.build(r.model, layout: layout)]) {
          expectFits(s);
          expectWellFormedSvg(sceneToSvg(s));
          expect(s.regions.length, r.model.facets.length);
        }
        if (r.model.facets.any((f) => f.isFlatRoofType)) {
          expect(_hatch(LengthDiagram.build(r.model, layout: layout)), isNotEmpty);
        }
      });
    }
  });

  final m = RoofMeasurement.parseAny(_json());

  group('parsing envelope 0.4', () {
    test('facets keep roof type, fit, borderline, support, points, rms and plane', () {
      final f5 = m.model.facets.firstWhere((f) => f.id == 'f5');
      expect(f5.roofType, 'pitched');
      expect(f5.pitchFit, 2.04);
      expect(f5.pitchSigma, 0.3);
      expect(f5.borderline, isTrue);
      expect(f5.isBorderline, isTrue);
      expect(f5.supportedPct, 84.0);
      expect(f5.points, 2000);
      expect(f5.rmsFt, 0.07);
      expect(f5.planEq, [0.17, 0, -8.5]);
      final f3 = m.model.facets.firstWhere((f) => f.id == 'f3');
      expect(f3.isFlatRoofType, isTrue);
      expect(f3.isBorderline, isFalse);
      // A facet whose kind is sloped (0.5/12 cut) but whose roof type is flat (2.0/12 cut).
      final f4 = m.model.facets.firstWhere((f) => f.id == 'f4');
      expect(f4.kind, FacetKind.sloped);
      expect(f4.isFlatRoofType, isTrue);
    });

    test('edges: the two new types and the jump in feet', () {
      final levels = m.model.edges.where((e) => e.type == EdgeType.levelChange).toList();
      expect(levels.map((e) => e.jumpFt), [2.5, 2.5, 0.4]);
      expect(m.model.edges.where((e) => e.type == EdgeType.flatEdge), hasLength(2));
      expect(m.model.edges.where((e) => e.type == EdgeType.ridge).single.jumpFt, isNull);
      expect(m.model.parseNotes, isEmpty);
      expect(m.model.totals.lengthsFt[EdgeType.flatEdge], 40.0);
      expect(m.model.totals.lengthsFt[EdgeType.levelChange], 48.0);
      expect(m.model.totals.extraLengths, isEmpty);
    });

    test('envelope totals carry the 0.4 keys, all nullable', () {
      final e = m.totals.engine!;
      expect(e.hasRoofing, isTrue);
      expect(e.roofingPitchedSquares, closeTo(10.48, 0.005));
      expect(e.roofingFlatSquares, closeTo(7.21, 0.005));
      expect(e.roofingPitchedSqft, closeTo(1048.4, 0.05));
      expect(e.roofingFlatSqft, closeTo(721.2, 0.05));
      expect(e.lowSlopeConfirmSqft, closeTo(243.5, 0.1));
      expect(e.areaSqftWallLine, isNotNull);
      expect(e.areaSqftRoofEdge, isNotNull);
      expect(e.outlinePerimeterWallFt, 224.0);
      expect(e.outlinePerimeterFt, 228.0);
      expect(e.overhangFtMedian, 1.1);
      expect(e.flatEdgeFt, 40.0);
      expect(e.levelChangeFt, 48.0);
      expect(e.planesSurfaceAreaSqft, closeTo(1769.6, 0.05));
      expect(e.complexity!.facets, 5);
      expect(e.complexity!.hint, 'simple');
      // The model's own totals carry the pitched and flat areas too.
      expect(m.model.totals.engine!.roofingFlatSqft, closeTo(721.2, 0.05));
    });

    test('quality and source.building', () {
      final q = m.model.quality!;
      expect(q.engine, 'planes/1');
      expect(q.fitAll, 0.82);
      expect(q.fitCovered, 0.9);
      expect(q.coverage, 0.93);
      expect(q.supportedPct, 90.0);
      expect(q.densityPtsM2, 9.5);
      expect(q.parcelMatch, 'exact');
      expect(q.outlineSource, 'county');
      expect(q.verdict, 'ok');
      expect(q.raw['overhang_scale'], 0.5);
      final b = m.model.building!;
      expect(b.parcelId, '0000000000');
      expect(b.outlineId, 'B-0001');
      expect(b.outlineCentroid, (x: 34.0000001, y: -118.0000001));
      expect(b.chosenBy, 'auto');
    });

    test('toJson round-trips the model and the envelope totals', () {
      final j = _json();
      final back = _viaText(m.toJson());
      expect(back['model']['facets'], j['model']['facets']);
      expect(back['model']['edges'], j['model']['edges']);
      expect(back['model']['quality'], j['model']['quality']);
      expect(back['model']['source'], j['model']['source']);
      expect(back['model']['totals']['lengths_ft'], j['model']['totals']['lengths_ft']);
      expect(back['model']['totals']['roofing_flat_sqft'], j['model']['totals']['roofing_flat_sqft']);
      expect(back['totals'], j['totals']);
      // And again: parse(toJson) is stable.
      expect(_viaText(RoofMeasurement.parseAny(back).toJson()), back);
    });

    test('facets and edges compare by value', () {
      final a = RoofModel.fromJson(_json()['model'] as Map<String, dynamic>);
      final b = RoofModel.fromJson(_json()['model'] as Map<String, dynamic>);
      expect(a.facets, b.facets);
      expect(a.facets.first.hashCode, b.facets.first.hashCode);
      expect(a.edges.last, b.edges.last);
      expect(a.edges.last.hashCode, b.edges.last.hashCode);
      expect(a.facets.first, isNot(a.facets.last));
      final j = _json();
      (j['model']['facets'][0] as Map)['borderline'] = true;
      expect(RoofModel.fromJson(j['model'] as Map<String, dynamic>).facets.first, isNot(a.facets.first));
      final k = _json();
      (k['model']['edges'][5] as Map)['jump_ft'] = 3.0;
      expect(RoofModel.fromJson(k['model'] as Map<String, dynamic>).edges[5], isNot(a.edges[5]));
    });

    test('an unknown edge type still reads as unspecified, noted', () {
      final j = _json();
      (j['model']['edges'][0] as Map)['type'] = 'gutter_run';
      final model = RoofModel.fromJson(j['model'] as Map<String, dynamic>);
      expect(model.edges.first.type, EdgeType.unspecified);
      expect(model.parseNotes.single, allOf(startsWith('edges[0].type'), contains('gutter_run')));
    });

    test('a wrongly typed 0.4 value is rejected with its path', () {
      final j = _json();
      (j['model']['facets'][0] as Map)['pitch_fit'] = 'steep';
      expect(() => RoofModel.fromJson(j['model'] as Map<String, dynamic>),
          throwsA(isA<FormatException>().having((e) => e.message, 'message', startsWith('facets[0].pitch_fit'))));
    });
  });

  group('old envelopes read exactly as before', () {
    final olds = loadEnvelopes();
    test('there are old envelopes to check', () => expect(olds, isNotEmpty));
    for (final f in olds.where((e) => e.name != 'synthetic_mixed_0.4')) {
      test('${f.name}: no 0.4 field appears, lengths_ft keeps its ten keys', () {
        final model = f.measurement.model;
        for (final facet in model.facets) {
          expect(facet.roofType, isNull);
          expect(facet.borderline, isNull);
          expect(facet.isBorderline, isFalse);
          expect(facet.isFlatRoofType, isFalse);
          expect(facet.toJson().containsKey('roof_type'), isFalse);
        }
        expect(model.totals.engine, isNull);
        expect(f.measurement.totals.engine, isNull);
        expect(model.building, isNull);
        final out = model.toJson();
        expect((out['totals'] as Map)['lengths_ft'] as Map, hasLength(10));
        expect(f.measurement.totals.toJson(), hasLength(14));
        expect(model.edges.where((e) => e.jumpFt != null), isEmpty);
      });
    }
  });

  group('hatchLines', () {
    test('clips to a concave polygon: every segment lies inside it', () {
      const l = <Pt>[(x: 0, y: 0), (x: 100, y: 0), (x: 100, y: 40), (x: 40, y: 40), (x: 40, y: 100), (x: 0, y: 100)];
      final lines = hatchLines(l, spacing: 6, width: 1, color: 0xFF000000);
      expect(lines.length, greaterThan(20));
      for (final s in lines) {
        for (final t in [0.1, 0.5, 0.9]) {
          final p = (x: s.a.x + (s.b.x - s.a.x) * t, y: s.a.y + (s.b.y - s.a.y) * t);
          expect(pointInPolygon(p, l), isTrue, reason: '$p');
        }
        expect((s.b.x - s.a.x) * (s.b.y - s.a.y) <= 0, isTrue, reason: 'rises to the right');
      }
    });

    test('degenerate input gives nothing', () {
      expect(hatchLines(const [(x: 0, y: 0), (x: 1, y: 1)], spacing: 5, width: 1, color: 0), isEmpty);
      expect(hatchLines(const [(x: 0, y: 0), (x: 9, y: 0), (x: 9, y: 9)], spacing: 0, width: 1, color: 0), isEmpty);
    });
  });

  for (final layout in ReportLayout.values) {
    group('diagrams ($layout)', () {
      final area = AreaDiagram.build(m.model, layout: layout);
      final length = LengthDiagram.build(m.model, layout: layout);

      test('flat facets are hatched inside their own outline, pitched ones are not', () {
        for (final s in [area, length]) {
          final lines = _hatch(s);
          expect(lines, isNotEmpty);
          for (final facetId in ['f1', 'f2', 'f5']) {
            final r = s.regions.firstWhere((r) => r.id == facetId);
            for (final l in lines) {
              final mid = (x: (l.a.x + l.b.x) / 2, y: (l.a.y + l.b.y) / 2);
              expect(pointInPolygon(mid, r.pts), isFalse, reason: 'hatch inside $facetId');
            }
          }
          // The two flat facets (f3, f4) carry the hatch; f3 is the larger one.
          final f3 = s.regions.firstWhere((r) => r.id == 'f3');
          expect(lines.where((l) => pointInPolygon((x: (l.a.x + l.b.x) / 2, y: (l.a.y + l.b.y) / 2), f3.pts)),
              isNotEmpty);
          expect(s.prims.whereType<PolyPrim>().any((p) => p.fill == DiagramStyle.report.flatRoofFill), isTrue);
        }
      });

      test('the borderline facet has its own outline; the area diagram says "Low slope"', () {
        expect(_borderlineOutlines(area), hasLength(1));
        expect(_borderlineOutlines(length), hasLength(1));
        // The compact page may have no room for the third line: the outline alone carries the flag there.
        if (layout == ReportLayout.wide) expect(_texts(area), contains(const RoofLabels().lowSlopeMarker));
        expect(_texts(length), isNot(contains(const RoofLabels().lowSlopeMarker)));
      });

      test('the marker text comes from the labels', () {
        final s = AreaDiagram.build(m.model, layout: layout, labels: const RoofLabels().copyWith({'low_slope_marker': 'Poca pendiente'}));
        if (layout == ReportLayout.wide) expect(_texts(s), contains('Poca pendiente'));
        expect(_texts(s), isNot(contains('Low slope')));
      });

      test('the legend lists the two new edge types with their lengths; level changes show their jump', () {
        final t = _texts(length);
        expect(t, containsAll(['Flat roof edges', 'Level changes', '40ft 0in', '48ft 0in']));
        // The jump text replaces the length on a level change edge, when the label has room.
        final jumps = t.where((x) => RegExp(r'^Step \d').hasMatch(x)).toList();
        if (layout == ReportLayout.wide) {
          expect(jumps, contains('Step 2ft 6in'));
        }
        for (final j in jumps) {
          expect(j, matches(RegExp(r'^Step \d+ft \d+in$')));
        }
      });

      test('new edge types are drawn in their own colour, a level change heavier', () {
        final st = DiagramStyle.report;
        final flat = length.prims.whereType<LinePrim>().where((p) => p.color == st.colorOf(EdgeType.flatEdge));
        final level = length.prims.whereType<LinePrim>().where((p) => p.color == st.colorOf(EdgeType.levelChange));
        expect(flat, isNotEmpty);
        expect(level, isNotEmpty);
        final eaves = length.prims.whereType<LinePrim>().where((p) => p.color == st.colorOf(EdgeType.eave));
        expect(level.map((p) => p.width).reduce((a, b) => a > b ? a : b),
            greaterThan(eaves.map((p) => p.width).reduce((a, b) => a > b ? a : b)));
        expect(st.colorOf(EdgeType.flatEdge), isNot(st.colorOf(EdgeType.unspecified)));
        expect({for (final t in EdgeType.values) st.colorOf(t)}, hasLength(EdgeType.values.length));
      });

      test('scenes fit, export to SVG, and facetAt finds the facet under a point', () {
        for (final s in [area, length]) {
          expectFits(s);
          expectWellFormedSvg(sceneToSvg(s));
          expect(s.regions.map((r) => r.id), ['f1', 'f2', 'f3', 'f4', 'f5']);
          for (final r in s.regions) {
            final cx = r.pts.map((p) => p.x).reduce((a, b) => a + b) / r.pts.length;
            final cy = r.pts.map((p) => p.y).reduce((a, b) => a + b) / r.pts.length;
            expect(s.facetAt((x: cx, y: cy)), r.id);
          }
          expect(s.facetAt((x: -50, y: -50)), isNull);
        }
      });
    });
  }

  group('old fixtures draw as before', () {
    for (final f in loadFixtures()) {
      for (final layout in ReportLayout.values) {
        test('${f.name} $layout: one prim per facet, no hatch, no marker, ten legend entries', () {
          final model = RoofModel.fromJson(f.json);
          final area = AreaDiagram.build(model, layout: layout);
          final length = LengthDiagram.build(model, layout: layout);
          for (final s in [area, length]) {
            expect(_hatch(s), isEmpty);
            expect(_borderlineOutlines(s), isEmpty);
            expect(s.prims.whereType<PolyPrim>().where((p) => p.fill == DiagramStyle.report.flatRoofFill), isEmpty);
          }
          final names = _texts(length);
          expect(names, isNot(contains('Flat roof edges')));
          expect(names, isNot(contains('Level changes')));
          expect(_texts(area), isNot(contains('Low slope')));
          const st = DiagramStyle.report;
          expect(length.prims.whereType<PolyPrim>().where((p) => p.fill == st.flatFill || p.fill == st.slopedFill),
              hasLength(model.facets.length));
        });
      }
    }
  });

  group('legend rows', () {
    test('ten entries keep the old layout, eleven and twelve fill column by column', () {
      expect(ReportLayout.wide.legendRowsFor(10), [4, 3, 3]);
      expect(ReportLayout.compact.legendRowsFor(10), [5, 5]);
      expect(ReportLayout.wide.legendRowsFor(11), [4, 4, 3]);
      expect(ReportLayout.wide.legendRowsFor(12), [4, 4, 4]);
      expect(ReportLayout.compact.legendRowsFor(11), [6, 5]);
      expect(ReportLayout.compact.legendRowsFor(12), [6, 6]);
    });
  });
}
