import 'dart:math' as math;

/// Which page geometry the diagrams and the summary are built for.
enum ReportLayout {
  /// 1600 x 1000 design size (landscape page or desktop): 3-column legend, 4-column figures.
  wide(designWidth: 1600, legendColumns: 3, figureColumns: 4, minLabelSize: 10),

  /// 800 x 1000 design size (phone width): 2-column legend and figures, labels never below
  /// [compactMinLabelSize] design pixels. Sizes are not scaled down, so text stays readable
  /// when the scene is shown at phone width.
  compact(designWidth: 800, legendColumns: 2, figureColumns: 2, minLabelSize: compactMinLabelSize);

  const ReportLayout({
    required this.designWidth,
    required this.legendColumns,
    required this.figureColumns,
    required this.minLabelSize,
  });

  /// Smallest label text, in design pixels, in the compact layout.
  static const double compactMinLabelSize = 14;

  final double designWidth;
  final int legendColumns, figureColumns;

  /// Smallest edge-length or facet label text, in scene pixels, before the label is hidden.
  final double minLabelSize;

  /// A text size of [design] design pixels at scale [k], never below 14 in the compact layout.
  double textSize(double design, double k) =>
      this == compact ? math.max(design * k, compactMinLabelSize) : design * k;

  /// Height of the default diagram scenes.
  double get designHeight => 1000;

  /// Legend rows per column for the ten edge types (wide 4 + 3 + 3, compact 5 + 5).
  List<int> get legendRows => this == wide ? const [4, 3, 3] : const [5, 5];

  /// Rows needed for [count] items in [columns] columns.
  static int rowsFor(int count, int columns) => (count + columns - 1) ~/ columns;
}

/// Scale factor of a scene of [width] x [height] relative to the layout's design size. The wide
/// layout shrinks down to 0.4; the compact layout is 1.0 at 800 wide and never below 0.8.
double layoutScale(ReportLayout layout, double width, double height) => switch (layout) {
      ReportLayout.wide => math.max(0.4, math.min(width / 1600, height / 1000)),
      ReportLayout.compact => math.max(0.8, math.min(width / 800, height / 1000)),
    };
