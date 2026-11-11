/// Roof model JSON, totals, diagram scenes (length, area, summary) and SVG export.
/// Pure Dart. PDF export lives in `package:bond_roof/roof_pdf.dart`.
library;

export 'src/area_diagram.dart' show AreaDiagram;
export 'src/format.dart' show feetInches, pitchLabel, sqft, wholeFeet;
export 'src/labels.dart' show RoofLabels;
export 'src/length_diagram.dart' show LengthDiagram, isHoleOutlineEdge;
export 'src/measurement.dart';
export 'src/metrics.dart' show textWidth;
export 'src/model.dart';
export 'src/report_layout.dart' show ReportLayout;
export 'src/scene.dart';
export 'src/style.dart' show DiagramStyle;
export 'src/summary_block.dart' show SummaryBlock;
export 'src/svg.dart' show sceneToSvg;
export 'src/totals_variants.dart' show RoofTotalsVariants;
