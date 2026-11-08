// Renders every model fixture to SVG and PDF in example/out/.
// Run from packages/bond_roof:  dart run example/render_fixtures.dart [font.ttf]
// ignore_for_file: avoid_print
import 'dart:convert';
import 'dart:io';

import 'package:bond_roof/bond_roof.dart';
import 'package:bond_roof/roof_pdf.dart';

Future<void> main(List<String> args) async {
  final font = args.isNotEmpty ? File(args.first).readAsBytesSync() : null;
  final out = Directory('example/out')..createSync(recursive: true);
  var count = 0;
  for (final dirPath in ['test/fixtures', '../../fixtures']) {
    final dir = Directory(dirPath);
    if (!dir.existsSync()) continue;
    final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    for (final f in files) {
      final j = jsonDecode(f.readAsStringSync());
      if (j is! Map<String, dynamic> || j['schema'] != 'bond.roof_model/0.1') {
        print('skip ${f.path} (schema ${j is Map ? j['schema'] : '?'})');
        continue;
      }
      final name = f.uri.pathSegments.last.replaceAll('.json', '');
      final m = RoofModel.fromJson(j);
      final len = LengthDiagram.build(m);
      final area = AreaDiagram.build(m);
      final sum = SummaryBlock.build(m);
      File('${out.path}/${name}_length.svg').writeAsStringSync(sceneToSvg(len));
      File('${out.path}/${name}_area.svg').writeAsStringSync(sceneToSvg(area));
      File('${out.path}/${name}_summary.svg').writeAsStringSync(sceneToSvg(sum));
      File('${out.path}/$name.pdf').writeAsBytesSync(
        await scenesToPdf([len, area, sum], fontTtf: font, title: 'Roof measurement report - ${m.address.display}'),
      );
      count++;
      print('$name: ${m.edges.length} edges, ${len.placedLabels} labels placed, ${len.hiddenLabels} hidden; '
          '${m.facets.length} facets, ${area.placedLabels} facet labels, ${area.hiddenLabels} hidden');
      print('  wrote ${name}_length.svg ${name}_area.svg ${name}_summary.svg $name.pdf');
    }
  }
  print('rendered $count fixtures into ${out.path}');
}
