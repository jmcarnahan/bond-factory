import 'package:flutter/material.dart';

/// Places an app's own [logo] at a fixed [size]. The kit never draws a brand
/// mark: the app passes a widget (an `Image`, an `SvgPicture`, a `CustomPaint`).
///
/// The box keeps its size at any system text size, and the mark is decorative
/// (hidden from screen readers) unless [semanticLabel] is given.
class BondLogoMark extends StatelessWidget {
  const BondLogoMark({super.key, required this.logo, this.size = 24, this.semanticLabel});

  final Widget logo;
  final double size;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final box = MediaQuery.withNoTextScaling(
      child: SizedBox(width: size, height: size, child: FittedBox(fit: BoxFit.contain, child: logo)),
    );
    if (semanticLabel != null) {
      return Semantics(label: semanticLabel, image: true, child: ExcludeSemantics(child: box));
    }
    return ExcludeSemantics(child: box);
  }
}
