import 'package:flutter/material.dart';
import 'package:bond_roof/bond_roof.dart';

import 'report.dart';
import 'scene_painter.dart';
import 'tokens.dart';

/// The three diagrams stacked vertically with headings, inline Print and
/// Save PDF buttons, and an inline status line. No dialogs or snackbars.
class RoofReportStrip extends StatefulWidget {
  const RoofReportStrip(this.model, {super.key, this.filename = 'roof-report.pdf'});

  final RoofModel model;
  final String filename;

  @override
  State<RoofReportStrip> createState() => _RoofReportStripState();
}

class _RoofReportStripState extends State<RoofReportStrip> {
  late List<Scene> _scenes = RoofReport.pages(widget.model);
  String? _status;
  bool _isError = false;
  bool _busy = false;

  @override
  void didUpdateWidget(RoofReportStrip old) {
    super.didUpdateWidget(old);
    if (!identical(old.model, widget.model)) {
      _scenes = RoofReport.pages(widget.model);
      _status = null;
      _isError = false;
    }
  }

  Future<void> _run(String working, String done, Future<void> Function() job) async {
    setState(() {
      _busy = true;
      _isError = false;
      _status = working;
    });
    try {
      await job();
      if (!mounted) return;
      setState(() {
        _status = done;
        _isError = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _status = 'Failed: $e';
        _isError = true;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: RoofUiTokens.gap,
          runSpacing: RoofUiTokens.gap,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            FilledButton.icon(
              onPressed: _busy
                  ? null
                  : () => _run('Preparing print view...', 'Print view opened.',
                      () => printReport(widget.model)),
              icon: const Icon(Icons.print),
              label: const Text('Print'),
            ),
            OutlinedButton.icon(
              onPressed: _busy
                  ? null
                  : () => _run('Building PDF...', 'PDF ready.',
                      () => shareReport(widget.model, filename: widget.filename)),
              icon: const Icon(Icons.picture_as_pdf),
              label: const Text('Save PDF'),
            ),
            if (_busy)
              const SizedBox(
                width: RoofUiTokens.gapLarge,
                height: RoofUiTokens.gapLarge,
                child: CircularProgressIndicator(),
              ),
            if (_status != null)
              Text(
                _status!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: _isError ? RoofUiTokens.error : RoofUiTokens.mutedText,
                ),
              ),
          ],
        ),
        for (var i = 0; i < _scenes.length; i++) ...[
          const SizedBox(height: RoofUiTokens.gapLarge),
          Text(RoofUiTokens.pageTitles[i], style: theme.textTheme.titleMedium),
          const SizedBox(height: RoofUiTokens.gap),
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(
                  color: RoofUiTokens.frame, width: RoofUiTokens.hairline),
            ),
            child: AspectRatio(
              aspectRatio: _scenes[i].width / _scenes[i].height,
              child: RoofDiagramView(_scenes[i]),
            ),
          ),
        ],
      ],
    );
  }
}
