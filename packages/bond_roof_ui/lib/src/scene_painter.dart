import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:bond_roof/bond_roof.dart';

import 'tokens.dart';

Color _argb(int v) => Color(v);

/// How a scene of [scene] size is placed in a box of [size]: uniform scale and the offset of its
/// top-left corner. Shared by the painter and the tap hit test so they always agree.
({double k, double dx, double dy}) sceneFit(Scene scene, Size size, BoxFit fit) {
  final sx = size.width / scene.width;
  final sy = size.height / scene.height;
  final k = fit == BoxFit.cover ? math.max(sx, sy) : math.min(sx, sy);
  return (k: k, dx: (size.width - scene.width * k) / 2, dy: (size.height - scene.height * k) / 2);
}

/// The id of the facet under [local] (a point in the box of [size] the scene is painted in), or
/// null (outside the scene, or on no facet).
String? facetIdAt(Scene scene, Size size, Offset local, {BoxFit fit = BoxFit.contain}) {
  if (scene.width <= 0 || scene.height <= 0 || size.isEmpty) return null;
  final f = sceneFit(scene, size, fit);
  if (f.k <= 0) return null;
  return scene.facetAt((x: (local.dx - f.dx) / f.k, y: (local.dy - f.dy) / f.k));
}

/// Paints a [Scene] with the canvas. Scene y is down; the scene is scaled
/// uniformly to fit the available size and centred.
class ScenePainter extends CustomPainter {
  const ScenePainter(this.scene, {this.fit = BoxFit.contain});

  final Scene scene;
  final BoxFit fit;

  @override
  void paint(Canvas canvas, Size size) {
    if (scene.width <= 0 || scene.height <= 0) return;
    final (:k, :dx, :dy) = sceneFit(scene, size, fit);
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    canvas.translate(dx, dy);
    canvas.scale(k);
    canvas.drawRect(
      Rect.fromLTWH(0, 0, scene.width, scene.height),
      Paint()..color = _argb(scene.background),
    );
    for (final p in scene.prims) {
      switch (p) {
        case LinePrim():
          _stroke(canvas, [_off(p.a), _off(p.b)], false, p.color, p.width, p.dashed);
        case PolyPrim():
          final pts = [for (final q in p.pts) _off(q)];
          if (pts.length < 2) break;
          if (p.fill != null) {
            canvas.drawPath(
              Path()..addPolygon(pts, true),
              Paint()
                ..style = PaintingStyle.fill
                ..isAntiAlias = true
                ..color = _argb(p.fill!),
            );
          }
          if (p.stroke != null) {
            _stroke(canvas, pts, true, p.stroke!, p.width, p.dashed);
          }
        case TextPrim():
          _text(canvas, p);
      }
    }
    canvas.restore();
  }

  static Offset _off(Pt p) => Offset(p.x, p.y);

  void _stroke(Canvas canvas, List<Offset> pts, bool close, int color,
      double width, bool dashed) {
    final path = Path()..addPolygon(pts, close);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..isAntiAlias = true
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = width
      ..color = _argb(color);
    if (!dashed) {
      canvas.drawPath(path, paint);
      return;
    }
    final on = RoofUiTokens.dashOn * math.max(width, 1);
    final off = RoofUiTokens.dashOff * math.max(width, 1);
    for (final m in path.computeMetrics()) {
      var d = 0.0;
      while (d < m.length) {
        final end = math.min(d + on, m.length);
        canvas.drawPath(m.extractPath(d, end), paint);
        d = end + off;
      }
    }
  }

  void _text(Canvas canvas, TextPrim p) {
    final tp = TextPainter(
      text: TextSpan(
        text: p.text,
        style: TextStyle(
          fontSize: p.size,
          color: _argb(p.color),
          fontWeight: p.bold ? FontWeight.w700 : FontWeight.w400,
          height: 1,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final ax = switch (p.anchor) {
      TextAnchor.start => 0.0,
      TextAnchor.middle => -tp.width / 2,
      TextAnchor.end => -tp.width,
    };
    canvas.save();
    canvas.translate(p.at.x, p.at.y);
    canvas.rotate(p.angleDeg * math.pi / 180);
    tp.paint(canvas, Offset(ax, -tp.height / 2));
    canvas.restore();
    tp.dispose();
  }

  @override
  bool shouldRepaint(ScenePainter old) =>
      !identical(old.scene, scene) || old.fit != fit;
}

/// Draws a [Scene] scaled to the available size.
///
/// With [onFacetTap] a tap on a facet reports its id (the scene must have been built from a model
/// with facets; the summary page has none). The package draws nothing on tap: the host attaches
/// its own inline controls.
class RoofDiagramView extends StatelessWidget {
  const RoofDiagramView(this.scene, {super.key, this.fit = BoxFit.contain, this.onFacetTap});

  final Scene scene;
  final BoxFit fit;

  /// Called with the id of the tapped facet. A tap outside every facet is ignored.
  final void Function(String facetId)? onFacetTap;

  @override
  Widget build(BuildContext context) {
    final paint = RepaintBoundary(
      child: CustomPaint(
        painter: ScenePainter(scene, fit: fit),
        size: Size.infinite,
        isComplex: true,
      ),
    );
    final tap = onFacetTap;
    if (tap == null) return paint;
    return LayoutBuilder(builder: (context, constraints) {
      final size = constraints.biggest;
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapUp: (d) {
          final id = facetIdAt(scene, size, d.localPosition, fit: fit);
          if (id != null) tap(id);
        },
        child: paint,
      );
    });
  }
}
