// Renders every model fixture (bare 0.x models and the models inside 0.2 envelopes) to SVG in
// both layouts, plus one PDF each, into ../../tmp/render/ (git-ignored).
// Run from packages/bond_roof:  dart run example/render_fixtures.dart [font.ttf]
// ignore_for_file: avoid_print
import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/roof_pdf.dart';

Future<void> main(List<String> args) async {
  final font = args.isNotEmpty ? File(args.first).readAsBytesSync() : null;
  final out = Directory('../../tmp/render')..createSync(recursive: true);
  var count = 0;
  for (final dirPath in ['test/fixtures', '../../fixtures']) {
    final dir = Directory(dirPath);
    if (!dir.existsSync()) continue;
    final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    for (final f in files) {
      final j = jsonDecode(f.readAsStringSync());
      final isModel = j is Map<String, dynamic> &&
          ((j['schema'] is String && (j['schema'] as String).startsWith('bond.roof_model/0.')) ||
              (j['contract'] is String && (j['contract'] as String).startsWith('bond.roof_model/')));
      if (!isModel) {
        print('skip ${f.path} (not a roof model or envelope)');
        continue;
      }
      final name = f.uri.pathSegments.last.replaceAll('.json', '');
      final m = RoofMeasurement.parseAny(j).model;
      for (final layout in ReportLayout.values) {
        final tag = '${name}_${layout.name}';
        final len = LengthDiagram.build(m, layout: layout);
        final area = AreaDiagram.build(m, layout: layout);
        final sum = SummaryBlock.build(m, layout: layout);
        File('${out.path}/${tag}_length.svg').writeAsStringSync(sceneToSvg(len));
        File('${out.path}/${tag}_area.svg').writeAsStringSync(sceneToSvg(area));
        File('${out.path}/${tag}_summary.svg').writeAsStringSync(sceneToSvg(sum));
        if (layout == ReportLayout.wide) {
          File('${out.path}/$name.pdf').writeAsBytesSync(
            await scenesToPdf([len, area, sum], fontTtf: font, title: '${const RoofLabels().pdfTitle} - ${m.address.display}'),
          );
        }
        print('$tag: ${m.edges.length} edges, ${len.placedLabels} labels placed, ${len.hiddenLabels} hidden; '
            '${m.facets.length} facets, ${area.placedLabels} facet labels, ${area.hiddenLabels} hidden');
      }
      count++;
    }
  }
  print('rendered $count fixtures (both layouts) into ${out.path}');
}
