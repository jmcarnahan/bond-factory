import 'model.dart';

/// Device-independent drawing primitives. Scenes are in logical pixels, y DOWN, colours ARGB.
sealed class Prim {
  const Prim();
}

class LinePrim extends Prim {
  const LinePrim({required this.a, required this.b, required this.color, this.width = 1, this.dashed = false});
  final Pt a, b;
  final int color;
  final double width;
  final bool dashed;
}

class PolyPrim extends Prim {
  const PolyPrim({required this.pts, this.fill, this.stroke, this.width = 1, this.dashed = false});
  final List<Pt> pts;
  final int? fill, stroke;
  final double width;
  final bool dashed;
}

enum TextAnchor { start, middle, end }

/// Text anchored at [at]: horizontally per [anchor], vertically centred on the line, rotated
/// [angleDeg] clockwise (screen convention) about [at].
class TextPrim extends Prim {
  const TextPrim({
    required this.at,
    required this.text,
    this.angleDeg = 0,
    required this.size,
    required this.color,
    this.anchor = TextAnchor.middle,
    this.bold = false,
  });
  final Pt at;
  final String text;
  final double angleDeg, size;
  final int color;
  final TextAnchor anchor;
  final bool bold;
}

class Scene {
  const Scene({
    required this.width,
    required this.height,
    required this.background,
    required this.prims,
    this.hiddenLabels = 0,
    this.placedLabels = 0,
    this.title = '',
  });
  final double width, height;
  final int background;
  final List<Prim> prims;

  /// Labels that were left off to avoid crowding (edge lengths, or facet labels).
  final int hiddenLabels;

  /// Labels that were drawn.
  final int placedLabels;
  final String title;
}
