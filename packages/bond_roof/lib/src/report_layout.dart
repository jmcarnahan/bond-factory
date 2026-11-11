import 'dart:math' as math;

/// Which page geometry the diagrams and the summary are built for.
enum ReportLayout {
  /// 1600 x 1000 design size (landscape page or desktop): 3-column legend, 4-column figures.
  wide(designWidth: 1600, designHeight: 1000, legendColumns: 3, figureColumns: 4, minLabelSize: 10),

  /// 400 x 500 design size for a phone-width card (about 358 px wide, scale 0.9): 2-column legend
  /// and figures. Text is sized so that nothing renders under 12 px at that card width: every
  /// text is at least [compactMinText] design px, edge and facet labels at least 14.
  compact(designWidth: 400, designHeight: 500, legendColumns: 2, figureColumns: 2, minLabelSize: 14);

  const ReportLayout({
    required this.designWidth,
    required this.designHeight,
    required this.legendColumns,
    required this.figureColumns,
    required this.minLabelSize,
  });

  /// Smallest text, in design pixels, in the compact layout (12 px rendered at 358/400 scale).
  static const double compactMinText = 13.5;

  final double designWidth, designHeight;
  final int legendColumns, figureColumns;

  /// Smallest edge-length or facet label text, in scene pixels, before the label is hidden.
  final double minLabelSize;

  /// Legend rows per column for the ten edge types (wide 4 + 3 + 3, compact 5 + 5).
  List<int> get legendRows => this == wide ? const [4, 3, 3] : const [5, 5];

  /// Rows needed for [count] items in [columns] columns.
  static int rowsFor(int count, int columns) => (count + columns - 1) ~/ columns;
}

/// Scale factor of a scene of [width] x [height] relative to the layout's design size. The wide
/// layout shrinks down to 0.4; the compact layout is 1.0 at 400 wide and never below 0.8.
double layoutScale(ReportLayout layout, double width, double height) => switch (layout) {
      ReportLayout.wide => math.max(0.4, math.min(width / 1600, height / 1000)),
      ReportLayout.compact => math.max(0.8, math.min(width / 400, height / 500)),
    };

/// Geometry and text sizes of one layout at scale [k]. Wide values are the original design
/// numbers times [k]; compact values are absolute design pixels (also times nothing: k is about 1).
class LayoutSpec {
  const LayoutSpec(this.layout, this.k);

  final ReportLayout layout;
  final double k;

  bool get compact => layout == ReportLayout.compact;
  double _v(double wide, double compactValue) => compact ? compactValue * k : wide * k;

  double get margin => _v(48, 16);
  double get titleY => _v(40, 22);
  double get titleSize => _v(25, 18);
  double get titleMin => _v(16, 14);
  double get captionY => _v(66, 38);
  double get captionSize => _v(14, 13.5);

  // Legend (length diagram).
  double get legendTop => _v(104, 62);
  double get legendPitch => _v(28, 20);
  double get legendSize => _v(16, 14);
  double get swatchLen => _v(34, 14);
  double get legendTextX => _v(46, 19);
  double get legendValueInset => _v(36, 6);
  double get legendPlanPad => _v(26, 14);

  // Plan area.
  double get planSide => _v(56, 10);
  double get planInsetX => _v(12, 4);
  double get planInsetTop => _v(18, 6);
  double get planInsetBottom => _v(12, 4);
  double get labelAreaSide => _v(8, 2);
  double get planBottomMin => _v(96, 70);

  // Area diagram header cells.
  double get areaHeaderTop => _v(96, 58);
  double get areaRowPitch => _v(58, 40);
  double get areaCaptionSize => _v(13, 13.5);
  double get areaValueSize => _v(22, 16);
  double get areaValueDy => _v(24, 17);
  double get areaPlanPad => _v(2, 4);

  // Compass and footer.
  double get compassRadius => _v(28, 14);
  double get compassInsetX => _v(76, 32);
  double get compassInsetY => _v(54, 36);
  double get northSize => _v(16, 13.5);
  double get northDy => _v(13, 11);
  double get footerSize => _v(13, 13.5);
  double get footerRight => _v(150, 56);
  double get footerBottom => _v(26, 10);

  // Summary block.
  double get sumTop => _v(44, 24);
  double get sumCaptionGap => _v(30, 20);
  double get sumTitleSize => _v(28, 18);
  double get sumTitleGap => _v(40, 26);
  double get figCaptionSize => _v(13, 13.5);
  double get figValueSize => _v(20, 16);
  double get figValueDy => _v(24, 18);
  double get figRowPitch => _v(66, 46);
  double get headingSize => _v(17, 14);
  double get headingGap => _v(26, 18);
  double get paraSize => _v(15, 13.5);
  double get paraIndent => _v(12, 6);
  double get bulletIndent => _v(30, 16);
  double get sectionGap => _v(12, 8);
  double get sumMinHeight => _v(240, 150);
  double get sumBottom => _v(24, 12);
}
