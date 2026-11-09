import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../primitives/bond_pressable.dart';
import '../tokens/tokens.dart';

/// "Sign in with Google" and, under it, the inline notice when the last
/// attempt did not sign anyone in. The page owns the sign-in call; this widget
/// only shows [label] and calls [onPressed].
///
/// The mark is an asset-free four-arc ring drawn from the tone colours in
/// [BondTokens], an approximation of the brand mark rather than a copy of it.
class BondGoogleSignInButton extends StatelessWidget {
  const BondGoogleSignInButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.notice,
    this.semanticsId = 'google-sign-in',
  });

  final String label;
  final VoidCallback? onPressed;

  /// "Sign-in is not configured on this build" and the like.
  final String? notice;
  final String? semanticsId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final enabled = onPressed != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BondPressable(
          onTap: onPressed,
          semanticLabel: label,
          semanticsId: semanticsId,
          borderRadius: BondRadius.r12All,
          color: enabled ? t.surface : t.line,
          minSize: BondLayout.minTap + BondSpace.s8,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: BondSpace.s16),
            decoration: BoxDecoration(
              borderRadius: BondRadius.r12All,
              border: Border.all(color: enabled ? t.lineStrong : t.line),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const _GoogleMark(),
                BondSpace.w8,
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: text.style(BondText.lead18, BondText.semibold, color: enabled ? t.ink : t.muted),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (notice != null) ...[
          BondSpace.h12,
          Semantics(
            identifier: semanticsId == null ? null : '$semanticsId-notice',
            liveRegion: true,
            child: Text(notice!, style: text.style(BondText.small14, BondText.medium, color: t.caution.press)),
          ),
        ],
      ],
    );
  }
}

class _GoogleMark extends StatelessWidget {
  const _GoogleMark();

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    return CustomPaint(
      size: const Size.square(BondLayout.icon),
      painter: _MarkPainter([t.info.base, t.danger.base, t.caution.base, t.positive.base]),
    );
  }
}

class _MarkPainter extends CustomPainter {
  const _MarkPainter(this.colors);

  final List<Color> colors;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = size.width * 0.2;
    final rect = Offset(stroke / 2, stroke / 2) & Size(size.width - stroke, size.height - stroke);
    // Four quarter arcs, clockwise from the right-hand side.
    for (var i = 0; i < colors.length; i++) {
      final paint = Paint()
        ..color = colors[i]
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke;
      canvas.drawArc(rect, -math.pi / 4 + i * math.pi / 2, math.pi / 2, false, paint);
    }
  }

  @override
  bool shouldRepaint(_MarkPainter old) => old.colors != colors;
}
