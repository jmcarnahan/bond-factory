import 'package:bond_roof/src/layout.dart';
import 'package:bond_roof/src/polylabel.dart';
import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

Pt p(double x, double y) => (x: x, y: y);

void main() {
  group('polylabel', () {
    test('square: centre, distance is half the side', () {
      final r = polylabel([[p(0, 0), p(10, 0), p(10, 10), p(0, 10)]], precision: 0.01);
      expect(r.point.x, closeTo(5, 0.1));
      expect(r.point.y, closeTo(5, 0.1));
      expect(r.distance, closeTo(5, 0.05));
    });

    test('L shape: pole sits at the inner corner, where the arms meet', () {
      final r = polylabel([[p(0, 0), p(10, 0), p(10, 2), p(2, 2), p(2, 10), p(0, 10)]], precision: 0.01);
      // Arms are 2 wide (radius 1); the reflex corner at (2, 2) allows a slightly larger circle.
      expect(r.distance, inInclusiveRange(1.0, 1.25));
      expect(r.point.x, lessThan(3));
      expect(r.point.y, lessThan(3));
    });

    test('hole pushes the pole into the ring, at a corner', () {
      final outer = [p(0, 0), p(10, 0), p(10, 10), p(0, 10)];
      final hole = [p(3, 3), p(3, 7), p(7, 7), p(7, 3)];
      final r = polylabel([outer, hole], precision: 0.01);
      // Ring is 3 wide; the corner circle touching both outer walls and the hole corner is bigger.
      expect(r.distance, closeTo(1.757, 0.05));
    });

    test('inside test', () {
      final tri = [p(0, 0), p(10, 0), p(0, 10)];
      expect(pointInPolygon(p(1, 1), tri), isTrue);
      expect(pointInPolygon(p(9, 9), tri), isFalse);
    });
  });

  group('Obb', () {
    test('overlap and rotation', () {
      const a = Obb(0, 0, 10, 2);
      expect(a.overlaps(const Obb(15, 0, 6, 2)), isTrue);
      expect(a.overlaps(const Obb(25, 0, 6, 2)), isFalse);
      // A thin box rotated 90 degrees through the middle.
      expect(a.overlaps(const Obb(0, 14, 10, 1, 1.5707963)), isFalse);
      expect(a.overlaps(const Obb(0, 10, 10, 1, 1.5707963)), isTrue);
    });

    test('segment crossing', () {
      const a = Obb(0, 0, 10, 2);
      expect(a.crossesSegment(p(-20, 0), p(20, 0)), isTrue);
      expect(a.crossesSegment(p(-20, 5), p(20, 5)), isFalse);
      expect(a.crossesSegment(p(-20, 3), p(20, 3), margin: 1.5), isTrue);
      expect(a.crossesSegment(p(0, -20), p(0, 20)), isTrue);
      expect(a.crossesSegment(p(30, -20), p(30, 20)), isFalse);
    });
  });

  group('LabelPlacer', () {
    final area = (l: 0.0, t: 0.0, r: 400.0, b: 300.0);

    test('hides a label wider than its edge', () {
      final edge = Seg(p(100, 100), p(110, 100));
      final placer = LabelPlacer(edges: [edge], area: area);
      expect(placer.placeAlong(edge, 30, 12, p(105, 200)), isNull);
    });

    test('puts the label outside, upright, and clear of its edge', () {
      final edge = Seg(p(100, 100), p(300, 100));
      final placer = LabelPlacer(edges: [edge], area: area);
      final box = placer.placeAlong(edge, 20, 12, p(200, 200))!;
      expect(box.cy, lessThan(100)); // centroid is below, so outward is up
      expect(box.angle, 0);
      expect(box.crossesSegment(edge.a, edge.b), isFalse);
    });

    test('flips an upside-down edge direction', () {
      final edge = Seg(p(300, 100), p(100, 100));
      final box = LabelPlacer(edges: [edge], area: area).placeAlong(edge, 20, 12, p(200, 200))!;
      expect(box.angle, closeTo(0, 1e-9));
    });

    test('falls back to the inside when the outside is blocked by another edge', () {
      final edge = Seg(p(100, 100), p(300, 100));
      final blocker = Seg(p(0, 88), p(400, 88));
      final placer = LabelPlacer(edges: [edge, blocker], area: area);
      final box = placer.placeAlong(edge, 20, 12, p(200, 200))!;
      expect(box.cy, greaterThan(100));
    });

    test('never overlaps an earlier label', () {
      final e1 = Seg(p(100, 100), p(300, 100));
      final placer = LabelPlacer(edges: [e1], area: area);
      final first = placer.placeAlong(e1, 20, 12, p(200, 200))!;
      final second = placer.placeAlong(e1, 20, 12, p(200, 200));
      expect(second == null || !second.overlaps(first), isTrue);
    });

    test('rejects positions outside the drawing area', () {
      final edge = Seg(p(100, 4), p(300, 4));
      final placer = LabelPlacer(edges: [edge], area: area);
      final box = placer.placeAlong(edge, 20, 12, p(200, 200))!;
      expect(box.cy, greaterThan(4)); // up would leave the area
    });
  });

  test('wrapText respects the width', () {
    final lines = wrapText('one two three four five six seven', 80, 12);
    expect(lines.length, greaterThan(1));
    expect(lines.join(' '), 'one two three four five six seven');
  });
}
