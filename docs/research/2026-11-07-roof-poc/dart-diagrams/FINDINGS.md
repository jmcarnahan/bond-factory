> Historical note: this prototype used the working names roof_model and roof_diagrams; they are now packages/bond_roof and packages/bond_roof_ui.

# Dart/Flutter diagrams and bond-factory packaging: findings

Scratch: S = (session scratch, not in repo)
Prototype: S/bf (bond-factory stand-in: workspace + roof_model + roof_diagrams), S/consA (path consumer), S/consB, S/consB2 (git consumers), S/out (rendered PNG/PDF/SVG).
Flutter 3.47.2, Dart 3.13.2. No file under ~/projects touched.

## 1. Rendering approach

FACT (pub.dev API, 2026-11-07): pdf 3.13.1 (Apache-2.0, pure Dart, web+wasm ready, sdk >=3.12), printing 5.15.1 (Apache-2.0, all 6 platforms incl. web, sdk >=3.12, flutter >=3.41), flutter_svg 2.3.2 (MIT, web ok, sdk ^3.11), vector_graphics 1.2.6 (BSD-3), vector_math 2.4.4 (BSD-3), xml 7.1.0.
NOTE: pdf/printing need Dart >=3.12, so every consumer toolchain must be Flutter >=3.45-ish (3.47.2 here is fine). Avalon pins sdk ^3.11.0 in pubspecs; that is a lower bound only and does not conflict.

What I built and RAN (all against one shared `Scene` of primitives: LinePrim, PolyPrim, TextPrim with rotation, 85-edge synthetic roof):
- roof_model (pure Dart, no Flutter): model + `buildLengthDiagram` + `sceneToSvg` + `sceneToPdf` (pdf package). `dart test`: 2 passed, `dart analyze` clean. Output S/out/length.pdf and length.svg, rasterised with pdftoppm and rsvg-convert: layouts identical, rotated labels correct in both.
- roof_diagrams (Flutter): `ScenePainter` (CustomPainter), `RoofSvgView` (flutter_svg), `printPdf`/`sharePdf` (printing). `flutter test` 2 passed, `flutter analyze` clean.
- consA app: `flutter build web --release` succeeded (2.2 MB main.dart.js, 40 MB build/web incl. CanvasKit); `flutter build ios --simulator --no-codesign` succeeded. Rendered the web build in headless Chrome: S/out/web.png shows both views.

Comparison:
| | (a) CustomPainter | (b) SVG string + flutter_svg | (c) pdf package + printing |
| web + iOS | yes (web run) | yes, BUT text fidelity issue | pdf: pure Dart. printing: web (browser print / download) and iOS (print + share sheet) per pub tags; I built both targets but did not run printing at runtime |
| rotated labels | yes, exact | rotated yes, but `dominant-baseline` is not parsed by vector_graphics_compiler (grep of parser.dart: only text-anchor handled) so rotated labels sit off-centre; visible in web.png bottom half vs top half | yes, via Matrix4 on PdfGraphics; verified in rendered PDF |
| print/save PDF | no, needs a second implementation | via PDF only, SVG itself does not print | native |
| text along edge | no true text-on-path anywhere; offset-and-rotate label is the Roofr look and works everywhere |
| collision handling | none built in, any approach needs our own layout |
| one code path for screen + print | needs (c) too | needs (c) too | the Scene is the single layout; three thin painters (Canvas, SVG string, PdfGraphics) of ~25 lines each |

INFERENCE/RECOMMENDATION: do NOT pick one renderer; pick one LAYOUT. Pure-Dart core builds a Scene (primitives in output units, labels already placed/rotated/hidden). Three trivial interpreters: Canvas (on-screen, most faithful), PDF (print/attach, `pdf` package), SVG (optional: email/web embed, test snapshots, avoids flutter_svg for display). Layout is not duplicated, only the ~25-line draw loops. A pure-Dart core with a thin Flutter package is viable and proven above (`dart test` works, no Flutter import in roof_model). Caveats:
- Text width must be measured identically for all outputs. I used one approximation function (0.56 em/char); good enough for digits and apostrophes. For exactness use the `pdf` package's PdfFont.stringMetrics (pure Dart) with an embedded TTF.
- The pdf package warned "Helvetica has no Unicode support" at runtime. Spanish text, degree signs or non-ASCII labels need an embedded TTF (avalon_ui already ships Figtree TTFs in assets, so the Flutter side can pass bytes into roof_model's toPdf).
- Colours: avalon's ui_token_gate bans raw Color(0x..) and numeric strokeWidth/fontSize in flutterui/packages/*/lib (tool/ui_token_gate.sh:4-19). External packages are outside that scan, but make the palette an injectable parameter so apps can pass AvColors.
- Popups: printing's `layoutPdf` opens the browser/OS print dialog, which is OS-owned and allowed by CLAUDE.md. Do not use any PdfPreview-in-dialog pattern or Tooltip; the no_popups regex (tool/no_popups_gate.sh:22) bans Tooltip/Dialog( etc.
- Web: printing on web loads pdf.js from a CDN for rasterised preview only (UNVERIFIED, from printing docs); layoutPdf/sharePdf do not need it.

## 2. Label layout

Built in S/bf/packages/roof_model/lib/src/scene.dart and run on 85 edges: 72 labels placed, 13 hidden, no label-label overlap.
Algorithm (FACT, it ran): edges sorted longest first; skip if screen length < 1.3 x text width; label centre = midpoint offset perpendicular by 0.9 x font size, side pointing away from roof centroid; angle normalised to [-90,90] so text is never upside down; oriented-box overlap test (SAT) against placed labels; reject on overlap; count hidden for the "some lengths hidden" footnote.
Known gap (FACT, visible in out/pdfr-1.png): labels are not tested against other EDGES, so short parallel edges 9 units apart get labels touching neighbouring lines. Fix: also test label boxes against edge segments (segment vs OBB), and try the opposite side before hiding. Pitch labels for facets can reuse the same box test.
Packages (pub.dev API):
| package | version | licence | note |
| vector_math | 2.4.4 | BSD-3 | Dart team; Vector2/Matrix4 only, no geometry algorithms |
| dart_jts | 0.3.0+1 (2023-11) | BSD-3 | JTS port: polygons, buffer, union, intersection, validity. Stale but works; candidate for geometry checks. dart_jts is not label placement |
| turf | 0.0.14 (2026-09) | MIT | GeoJSON ops (area, length, bbox, centroid); geographic, not planar feet |
| polylabel | 1.0.1 (2021, sdk <3.0.0) | BSD-3 | visual-centre algorithm; SDK constraint blocks Dart 3 pubs. Port is ~80 lines, copy it |
| xml | 7.1.0 | MIT | only if parsing SVG |
Nothing on pub.dev does callout/label placement; write it (done above, ~60 lines).

## 3. Monorepo packaging

FACT, existing houses:
- avalon-crm/flutterui/pubspec.yaml:1-10: root `name: avalon_workspace`, `publish_to: none`, `environment: sdk: ^3.11.0`, `workspace:` listing 5 members. Members have `resolution: workspace` and depend on siblings by `path:` (apps/office_web/pubspec.yaml:12-17: `avalon_core: path: ../../packages/avalon_core`).
- paga-time/flutterui/pubspec.yaml:1-11: same shape plus `flutter: '>=3.41.0'` in the root environment; members pt_core, pt_ui, apps.
FACT, tested:
1. consA: separate workspace, `path: ../../../bf/packages/roof_diagrams` (path into another repo/workspace whose packages carry `resolution: workspace`): `pub get` OK, web build OK, iOS simulator build OK. The dependency's own lockfile/overrides are ignored; the consumer resolves everything. The bf root pubspec is not read.
2. consB: `git: {url, path: packages/roof_diagrams, ref: <tag>}` for roof_diagrams. roof_diagrams has `roof_model: path: ../roof_model`; pub treats that sibling as a git dep of the SAME repo and commit. If the app also lists roof_model directly with `ref: v0.1.0` (tag), resolution FAILS ("roof_model from git ... at 6c0673f is required"). With `ref: <full commit SHA>` for both it resolves; lockfile records ref and resolved-ref. Simplest: the app depends only on roof_diagrams and roof_diagrams re-exports roof_model (consB2 resolved fine). Pins: `ref` accepts tag/branch/SHA; pubspec.lock pins resolved-ref SHA; `flutter pub upgrade roof_diagrams` moves it.
3. `dart pub get` inside bf prints "Deleting old lock-file" for member lockfiles: one lock at the root only (doc: https://dart.dev/tools/pub/workspaces). Glob `packages/*` in `workspace:` needs Dart 3.11+ (doc), fine here.
Caveats (FACT unless marked):
- path dep across repos: bond-factory must be checked out at the same relative path on every machine, in CI, in Docker and on Railway/Vercel builds. Breaks silently on a fresh clone (INFERENCE: nobody has it). Good for local co-development only.
- git dep: needs credentials for a private repo in CI (INFERENCE: SSH key or token; not tested). Reproducible via SHA. Each change needs commit + tag + bump in each app.
- Both need Flutter >=3.45-ish because of pdf/printing sdk >=3.12.
Recommendation (INFERENCE): bond-factory is its own pub workspace (it has 2+ packages sharing deps; one lock; analysis in one context). Plain `dart pub workspaces`, not melos (melos 8.10.1, sdk ^3.9, adds bootstrap/scripts you do not need; the existing repos use only make). Apps use git+SHA in committed pubspecs for CI/deploy and a local `pubspec_overrides.yaml` with path: to the sibling checkout for co-development (pub supports pubspec_overrides.yaml for non-workspace roots; for a workspace member use `dependency_overrides` in the workspace ROOT pubspec; UNTESTED here).

Bond-factory root pubspec.yaml:
```yaml
name: bond_factory_workspace
publish_to: none
environment:
  sdk: ^3.11.0
  flutter: '>=3.41.0'
workspace:
  - packages/*        # or list roof_model, roof_diagrams
```
Member (pure Dart): packages/roof_model/pubspec.yaml
```yaml
name: roof_model
publish_to: none
resolution: workspace
environment:
  sdk: ^3.11.0
dependencies:
  pdf: ^3.13.1
  vector_math: ^2.4.4
dev_dependencies:
  lints: ^6.0.0
  test: ^1.25.6
```
Member (Flutter): packages/roof_diagrams/pubspec.yaml
```yaml
name: roof_diagrams
publish_to: none
resolution: workspace
environment:
  sdk: ^3.11.0
  flutter: '>=3.41.0'
dependencies:
  flutter: {sdk: flutter}
  roof_model: {path: ../roof_model}
  flutter_svg: ^2.3.2        # only if the SVG view is kept
  printing: ^5.15.1
dev_dependencies:
  flutter_test: {sdk: flutter}
  flutter_lints: ^6.0.0
```
Consumer (e.g. avalon_screens or crew_mobile pubspec in avalon-crm):
```yaml
dependencies:
  roof_diagrams:
    git:
      url: https://github.com/<org>/bond-factory.git
      path: packages/roof_diagrams
      ref: <40-char commit SHA>
```
Dev-time alternative (tested form): `roof_diagrams: {path: ../../../bond-factory/packages/roof_diagrams}`.
Pure-Dart service or script use: depend on roof_model only, git + path: packages/roof_model, same SHA.

## 4. House conventions to mirror

- analysis_options.yaml (flutterui/analysis_options.yaml:1-16): include package:flutter_lints/flutter.yaml; exclude **/gen/**, **/build/**; rules prefer_const_constructors, avoid_print, always_declare_return_types, unawaited_futures, use_build_context_synchronously, prefer_final_locals. Per-package files just `include: ../../analysis_options.yaml` plus an `exclude: build/**` (packages/avalon_core/analysis_options.yaml). paga-time's root file is identical. Pure-Dart package: use `lints` instead of flutter_lints (I did) but keep the same six rules.
- pubspec: `publish_to: none`, `resolution: workspace`, `sdk: ^3.11.0`, `flutter: '>=3.41.0'` only on Flutter packages; exact-pinned versions for plugins in apps/core (e.g. firebase_auth: 6.7.0) and caret for stable pure packages.
- No codegen: tool/ui_token_gate.sh bans build_runner, freezed, json_serializable, google_fonts in pubspecs. Hand-written fromJson (as in the prototype). Do not add them to bond-factory if apps will lint its pubspec-style.
- Tests: flutter test per package (make/flutter.mk:test-pkg), contract tests against fixtures (packages/avalon_core/test/*_fixtures_contract_test.dart). Mirror: roof_model has `dart test` with JSON fixtures emitted by the Python service as the contract.
- No popups: no_popups_gate.sh scans packages/*/lib and apps/*/lib only, regex line 22. bond-factory needs its own copy of the gate and a source-guard test like packages/avalon_ui/test/source_guards_test.dart. Print via OS print dialog is allowed.
- Token gate: no raw Color/fontSize/strokeWidth numerics outside tokens; take palette and sizes as constructor parameters.
- Makefile: avalon uses make/flutter.mk targets (test-flutter, gates, analyze). Add equivalent make targets to bond-factory.
- PDFs in avalon today (FACT): server side only. backend/avalon/services/pdf.py renders Jinja2 templates (backend/avalon/templates/estimate.html etc.) through WeasyPrint (backend/pyproject.toml:26, weasyprint ^68.1), stores a DocumentRecord keyed by content hash, and serves GET /estimates/{id}/pdf and POST /estimates/{id}/pdf-link (backend/avalon/rest/routers/estimates.py:175,190). No Dart code in flutterui/ generates PDFs (grep of packages/ and apps/ finds only API calls to pdf-link). pdf.py's data_only_fetcher (pdf.py:~55) permits only data: URLs.
  INFERENCE: two fits. (A) Client makes the PDF with roof_model's toPdf and uploads it as a job attachment (property photos/uploads path). (B) Preferred for estimates: the Python service already has the geometry, so it can emit the SVG (port of the same scene logic) or the app sends the SVG string, and WeasyPrint embeds it as <img src="data:image/svg+xml;base64,..."> in estimate.html, keeping one PDF pipeline. Because the Scene logic would then exist twice (Dart and Python), pick ONE owner of layout: either Python emits the finished scene/SVG (apps only display it, then Dart need only a viewer), or Dart owns layout and uploads PNG/PDF. This is the main architecture decision for the team lead.

## 5. Names and API (signatures only)

Packages: `roof_model` (pure Dart: model, geometry helpers, scene, svg, pdf export; lib/roof_model.dart + lib/roof_pdf.dart so web apps that skip PDF do not pull `pdf`), `roof_diagrams` (Flutter: widgets, printing glue).
```dart
// roof_model
class RoofModel { factory RoofModel.fromJson(Map<String, dynamic> j); List<RoofFacet> facets; List<RoofEdge> edges; List<RoofHole> holes; RoofTotals get totals; }
class RoofTotals { double totalAreaSqft; double pitchedAreaSqft; double flatAreaSqft; String predominantPitch; double get squares; Map<EdgeType,double> lengthFt; }
enum EdgeType { eave, rake, ridge, hip, valley, stepFlashing, wallFlashing, parapet, transition }
sealed class Prim; class LinePrim; class PolyPrim; class TextPrim; class Scene { double width, height; List<Prim> prims; int hiddenLabels; }
class DiagramStyle { Map<EdgeType,int> colors; double fontSize; double minLabelPx; String Function(double ft) formatLength; List<int> Function(String pitch) areaFill; }
class LengthDiagram { static Scene build(RoofModel m, {double width, double height, DiagramStyle style}); }  // + legend of totals per type
class AreaDiagram   { static Scene build(RoofModel m, {double width, double height, DiagramStyle style}); }
class SummaryBlock  { static Scene build(RoofModel m, {double width, DiagramStyle style}); }
String sceneToSvg(Scene s);                         // roof_model.dart
Future<Uint8List> scenesToPdf(List<Scene> pages, {Uint8List? fontTtf}); // roof_pdf.dart
// roof_diagrams
class RoofDiagramView extends StatelessWidget { const RoofDiagramView(Scene scene, {Key? key}); }
Future<void> printScenes(List<Scene> s);  Future<void> shareScenes(List<Scene> s, String filename);
```

## Could not determine
- printing's runtime behaviour on web (print dialog, share) and iOS (share sheet): only built, not executed.
- Whether pubspec_overrides or root dependency_overrides is the cleanest local-dev switch for a workspace member (not tested).
- CI credentials for a private git dependency (not tested).
- Exact font metrics parity between Helvetica in PDF, system font in Flutter and Arial in SVG: approximated, not measured.
- Label-vs-edge collision and hole/skylight labelling: not implemented.
