import 'model.dart';
import 'scene.dart';
import 'hatch.dart';
import 'style.dart';

/// Adds one facet to [prims]: a facet typed `flat` (envelope 0.4) gets the neutral fill and a
/// hatch, any other facet the fill of its [FacetKind]; a borderline one is outlined in
/// [DiagramStyle.borderlineStroke]. A facet without the 0.4 keys is drawn as before.
void addFacetPrims(
  List<Prim> prims,
  RoofFacet f,
  List<Pt> pts,
  DiagramStyle style, {
  required int stroke,
  required double strokeWidth,
  required double k,
}) {
  final outline = f.isBorderline ? style.borderlineStroke : stroke;
  final outlineW = f.isBorderline ? strokeWidth * 1.8 + 1 : strokeWidth;
  if (!f.isFlatRoofType) {
    prims.add(PolyPrim(
      pts: pts,
      fill: f.kind == FacetKind.flat ? style.flatFill : style.slopedFill,
      stroke: outline,
      width: outlineW,
    ));
    return;
  }
  prims
    ..add(PolyPrim(pts: pts, fill: style.flatRoofFill))
    ..addAll(hatchLines(pts, spacing: 9 * k, width: 1.6 * k, color: style.hatchColor))
    ..add(PolyPrim(pts: pts, stroke: outline, width: outlineW));
}
