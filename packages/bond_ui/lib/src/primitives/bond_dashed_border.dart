import 'package:flutter/material.dart';

import '../tokens/tokens.dart';

/// Draws a dashed rounded border around [child]. Marks tentative rows and
/// empty slots.
class BondDashedBorder extends StatelessWidget {
  const BondDashedBorder({
    super.key,
    required this.child,
    this.color,
    this.radius,
    this.fill,
  });

  final Widget child;

  /// Dash colour; defaults to the strong line token.
  final Color? color;
  /// Corner radius; defaults to the shape token `r12`.
  final double? radius;
  final Color? fill;

  @override
  Widget build(BuildContext context) => CustomPaint(
        foregroundPainter: _DashPainter(
          color: color ?? BondTokens.of(context).lineStrong,
          radius: radius ?? BondTokens.of(context).shape.r12,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(
                radius ?? BondTokens.of(context).shape.r12),
          ),
          child: child,
        ),
      );
}

class _DashPainter extends CustomPainter {
  _DashPainter({required this.color, required this.radius});

  final Color color;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = BondLayout.hairline;
    final rect = RRect.fromRectAndRadius(
      (Offset.zero & size).deflate(BondLayout.hairline / 2),
      Radius.circular(radius),
    );
    final path = Path()..addRRect(rect);
    for (final metric in path.computeMetrics()) {
      var d = 0.0;
      while (d < metric.length) {
        canvas.drawPath(
            metric.extractPath(d, d + BondLayout.dashLength), paint);
        d += BondLayout.dashLength * 2;
      }
    }
  }

  @override
  bool shouldRepaint(_DashPainter old) =>
      old.color != color || old.radius != radius;
}
