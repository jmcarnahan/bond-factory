import 'model.dart';

const _defaultEdgeColors = <EdgeType, int>{
  EdgeType.eave: 0xFF2E7D32,
  EdgeType.ridge: 0xFF8BC34A,
  EdgeType.hip: 0xFF5E35B1,
  EdgeType.valley: 0xFFE53935,
  EdgeType.rake: 0xFFFBC02D,
  EdgeType.stepFlashing: 0xFF8D6E63,
  EdgeType.wallFlashing: 0xFF1E88E5,
  EdgeType.parapet: 0xFFFB8C00,
  EdgeType.transition: 0xFFD81B60,
  EdgeType.unspecified: 0xFF26A69A,
};

const _defaultDashed = <EdgeType>{EdgeType.stepFlashing, EdgeType.wallFlashing};

/// Colours (ARGB) and sizes for the diagrams. Sizes are for a 1600 px wide scene and scale
/// with the scene.
class DiagramStyle {
  const DiagramStyle({
    Map<EdgeType, int>? edgeColors,
    Set<EdgeType>? dashedTypes,
    this.flatFill = 0xFFE3F2FD,
    this.slopedFill = 0xFFFFF8E1,
    this.holeStroke = 0xFF1E88E5,
    this.fontSize = 15,
    this.minLabelPx = 6,
    this.strokeWidth = 3,
    this.textColor = 0xFF212121,
    this.background = 0xFFFFFFFF,
  })  : edgeColors = edgeColors ?? _defaultEdgeColors,
        dashedTypes = dashedTypes ?? _defaultDashed;

  /// The contract palette.
  static const DiagramStyle report = DiagramStyle();

  final Map<EdgeType, int> edgeColors;
  final Set<EdgeType> dashedTypes;
  final int flatFill, slopedFill, holeStroke;
  final double fontSize;

  /// Edges shorter than this many pixels (at 1600 px wide) never get a length label. Longer
  /// ones still need to be at least half as long as the label text.
  final double minLabelPx;
  final double strokeWidth;
  final int textColor, background;

  int colorOf(EdgeType t) => edgeColors[t] ?? 0xFF607D8B;
}
