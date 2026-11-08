// Port of polylabel (https://github.com/mapbox/polylabel), a fast algorithm for finding the
// pole of inaccessibility of a polygon. Original work Copyright (c) 2016 Mapbox, ISC licence:
// permission to use, copy, modify and/or distribute this software for any purpose with or
// without fee is hereby granted, provided that this notice appears in all copies. The software
// is provided "as is" without warranty of any kind.
import 'dart:math' as math;

import 'model.dart';

class _Cell {
  _Cell(this.x, this.y, this.h, List<List<Pt>> rings)
      : d = _pointToPolygonDist(x, y, rings),
        max = 0 {
    max = d + h * math.sqrt2;
  }
  final double x, y, h, d;
  double max;
}

double _segDistSq(double px, double py, Pt a, Pt b) {
  var x = a.x, y = a.y;
  final dx = b.x - x, dy = b.y - y;
  if (dx != 0 || dy != 0) {
    final t = ((px - x) * dx + (py - y) * dy) / (dx * dx + dy * dy);
    if (t > 1) {
      x = b.x;
      y = b.y;
    } else if (t > 0) {
      x += dx * t;
      y += dy * t;
    }
  }
  final ex = px - x, ey = py - y;
  return ex * ex + ey * ey;
}

/// Signed distance from (x, y) to the polygon outline: positive inside.
double _pointToPolygonDist(double x, double y, List<List<Pt>> rings) {
  var inside = false;
  var minDistSq = double.infinity;
  for (final ring in rings) {
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      final a = ring[i], b = ring[j];
      if ((a.y > y) != (b.y > y) && x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x) inside = !inside;
      minDistSq = math.min(minDistSq, _segDistSq(x, y, a, b));
    }
  }
  return minDistSq == 0 ? 0 : (inside ? 1 : -1) * math.sqrt(minDistSq);
}

/// True when [p] is inside the polygon (ray casting).
bool pointInPolygon(Pt p, List<Pt> poly) => _pointToPolygonDist(p.x, p.y, [poly]) > 0;

/// Distance from [p] to the polygon outline, positive inside, negative outside.
double signedDistanceToPolygon(Pt p, List<Pt> poly) => _pointToPolygonDist(p.x, p.y, [poly]);

_Cell _centroidCell(List<List<Pt>> rings) {
  var area = 0.0, x = 0.0, y = 0.0;
  final pts = rings.first;
  for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    final a = pts[i], b = pts[j];
    final f = a.x * b.y - b.x * a.y;
    x += (a.x + b.x) * f;
    y += (a.y + b.y) * f;
    area += f * 3;
  }
  if (area == 0) return _Cell(pts.first.x, pts.first.y, 0, rings);
  return _Cell(x / area, y / area, 0, rings);
}

/// Pole of inaccessibility of the polygon [rings] (outer ring first, then holes), found to
/// within [precision] (same units as the coordinates). Returns the point and its distance to
/// the nearest outline.
({Pt point, double distance}) polylabel(List<List<Pt>> rings, {double precision = 0.5}) {
  final outer = rings.first;
  var minX = double.infinity, minY = double.infinity, maxX = -double.infinity, maxY = -double.infinity;
  for (final p in outer) {
    minX = math.min(minX, p.x);
    minY = math.min(minY, p.y);
    maxX = math.max(maxX, p.x);
    maxY = math.max(maxY, p.y);
  }
  final width = maxX - minX, height = maxY - minY;
  final cellSize = math.min(width, height);
  var h = cellSize / 2;
  if (cellSize == 0) return (point: (x: minX, y: minY), distance: 0.0);

  // Max-heap on _Cell.max.
  final heap = <_Cell>[];
  void push(_Cell c) {
    heap.add(c);
    var i = heap.length - 1;
    while (i > 0) {
      final parent = (i - 1) ~/ 2;
      if (heap[parent].max >= heap[i].max) break;
      final t = heap[parent];
      heap[parent] = heap[i];
      heap[i] = t;
      i = parent;
    }
  }

  _Cell pop() {
    final top = heap.first;
    final last = heap.removeLast();
    if (heap.isNotEmpty) {
      heap[0] = last;
      var i = 0;
      while (true) {
        final l = 2 * i + 1, r = l + 1;
        var m = i;
        if (l < heap.length && heap[l].max > heap[m].max) m = l;
        if (r < heap.length && heap[r].max > heap[m].max) m = r;
        if (m == i) break;
        final t = heap[m];
        heap[m] = heap[i];
        heap[i] = t;
        i = m;
      }
    }
    return top;
  }

  for (var x = minX; x < maxX; x += cellSize) {
    for (var y = minY; y < maxY; y += cellSize) {
      push(_Cell(x + h, y + h, h, rings));
    }
  }

  var best = _centroidCell(rings);
  final bboxCell = _Cell(minX + width / 2, minY + height / 2, 0, rings);
  if (bboxCell.d > best.d) best = bboxCell;

  while (heap.isNotEmpty) {
    final cell = pop();
    if (cell.d > best.d) best = cell;
    if (cell.max - best.d <= precision) continue;
    h = cell.h / 2;
    push(_Cell(cell.x - h, cell.y - h, h, rings));
    push(_Cell(cell.x + h, cell.y - h, h, rings));
    push(_Cell(cell.x - h, cell.y + h, h, rings));
    push(_Cell(cell.x + h, cell.y + h, h, rings));
  }
  return (point: (x: best.x, y: best.y), distance: best.d);
}
