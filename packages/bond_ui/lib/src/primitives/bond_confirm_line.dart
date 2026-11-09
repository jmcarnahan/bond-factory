import 'package:flutter/material.dart';

import '../tokens/tokens.dart';
import 'bond_pressable.dart';

/// Text scale above which the two actions stack (1.25 times the base size).
const double kStackTextScale = 1.25;

/// The two-action line of [BondConfirm]: a coloured first action and a plain
/// second one. Side by side with a dot between them while all three fit on
/// one line; otherwise stacked with no dot, so the dot never sits alone.
class BondConfirmLine extends StatelessWidget {
  const BondConfirmLine({
    super.key,
    required this.first,
    required this.firstColor,
    required this.onFirst,
    required this.second,
    required this.onSecond,
    this.stacked = false,
    this.firstId,
    this.secondId,
  });

  final String first;
  final Color firstColor;
  final VoidCallback? onFirst;
  final String second;
  final VoidCallback onSecond;
  final bool stacked;
  final String? firstId;
  final String? secondId;

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final text = BondText(t);
    final firstStyle =
        text.style(BondText.small14, BondText.semibold, color: firstColor);
    final secondStyle = text.style(BondText.small14, BondText.semibold);
    final largeText = MediaQuery.textScalerOf(context).scale(BondText.base16) >
        BondText.base16 * kStackTextScale;

    Widget action(String label, TextStyle style, VoidCallback? tap, String? id,
            {bool pad = true}) =>
        BondPressable(
          onTap: tap,
          semanticLabel: label,
          semanticsId: id,
          minSize: BondLayout.minTap,
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: pad ? BondSpace.s8 : 0),
            // widthFactor 1: shrink to the text in a Wrap, so the two
            // actions share a line instead of each filling it.
            child: Center(widthFactor: 1, child: Text(label, style: style)),
          ),
        );

    if (stacked || largeText) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          action(first, firstStyle, onFirst, firstId, pad: false),
          action(second, secondStyle, onSecond, secondId, pad: false),
        ],
      );
    }
    return LayoutBuilder(builder: (context, box) {
      final scaler = MediaQuery.textScalerOf(context);
      final dir = Directionality.of(context);
      double width(String s, TextStyle st) {
        final tp = TextPainter(
          text: TextSpan(text: s, style: st),
          textDirection: dir,
          textScaler: scaler,
          maxLines: 1,
        )..layout();
        final w = tp.width;
        tp.dispose();
        return w;
      }

      const pad = BondSpace.s8 * 2;
      final needed = width(first, firstStyle) +
          pad +
          width('·', text.small) +
          width(second, secondStyle) +
          pad;
      if (!box.maxWidth.isInfinite && needed > box.maxWidth) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            action(first, firstStyle, onFirst, firstId),
            action(second, secondStyle, onSecond, secondId),
          ],
        );
      }
      return Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          action(first, firstStyle, onFirst, firstId),
          Text('·', style: text.small),
          action(second, secondStyle, onSecond, secondId),
        ],
      );
    });
  }
}
