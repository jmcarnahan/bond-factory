import 'package:flutter/material.dart';
import 'package:bond_roof/bond_roof.dart';

import 'report.dart';
import 'scene_painter.dart';
import 'tokens.dart';
import 'totals_table.dart';

/// The report as an inline strip: Print, Save PDF and Share PDF buttons with an inline status
/// line, the totals table, then the length diagram, the area diagram and the summary stacked
/// vertically with headings. No dialogs, snackbars or tooltips.
///
/// Pass exactly one of [model] or [measurement]. Below [RoofUiTokens.compactBreakpoint] logical
/// pixels of width the scenes are built with [ReportLayout.compact]. Scenes are cached per
/// layout and rebuilt only when the model (by identity) or the [labels] change.
class RoofReportStrip extends StatefulWidget {
  const RoofReportStrip({
    super.key,
    this.model,
    this.measurement,
    this.labels = const RoofLabels(),
    this.filename = 'roof-report.pdf',
    this.showActions = true,
    this.showTotals = true,
    this.onStatus,
  }) : assert((model == null) != (measurement == null), 'pass exactly one of model or measurement');

  final RoofModel? model;
  final RoofMeasurement? measurement;

  /// Every string the strip, its diagrams and the PDF print.
  final RoofLabels labels;

  /// The file name offered by Save PDF and Share PDF.
  final String filename;

  /// Show the Print, Save PDF and Share PDF buttons with the status line.
  final bool showActions;

  /// Show the [RoofTotalsTable] above the diagrams.
  final bool showTotals;

  /// Called with each inline status text (building, done, failed).
  final void Function(String status)? onStatus;

  @override
  State<RoofReportStrip> createState() => _RoofReportStripState();
}

class _RoofReportStripState extends State<RoofReportStrip> {
  final Map<ReportLayout, List<Scene>> _scenes = {};
  RoofMeasurement? _wrapped;
  String? _status;
  bool _isError = false;
  bool _busy = false;

  RoofModel get _model => widget.model ?? widget.measurement!.model;

  RoofMeasurement get _measurement {
    final given = widget.measurement;
    if (given != null) return given;
    final w = _wrapped;
    if (w != null && identical(w.model, widget.model)) return w;
    return _wrapped = RoofMeasurement.fromModel(widget.model!);
  }

  List<Scene> _scenesFor(ReportLayout layout) =>
      _scenes[layout] ??= RoofReport.pages(_model, labels: widget.labels, layout: layout);

  @override
  void didUpdateWidget(RoofReportStrip old) {
    super.didUpdateWidget(old);
    final oldModel = old.model ?? old.measurement!.model;
    if (!identical(oldModel, _model) || old.labels != widget.labels) {
      _scenes.clear();
    }
    if (!identical(oldModel, _model)) {
      _status = null;
      _isError = false;
    }
  }

  void _setStatus(String text, {bool error = false}) {
    setState(() {
      _status = text;
      _isError = error;
    });
    widget.onStatus?.call(text);
  }

  Future<void> _run(String working, String done, Future<void> Function() job) async {
    setState(() => _busy = true);
    _setStatus(working);
    try {
      await job();
      if (!mounted) return;
      _setStatus(done);
    } catch (e) {
      if (!mounted) return;
      _setStatus(RoofLabels.fill(widget.labels.statusFailed, {'error': '$e'}), error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _actions(ThemeData theme) {
    final l = widget.labels;
    return Wrap(
      spacing: RoofUiTokens.gap,
      runSpacing: RoofUiTokens.gap,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        FilledButton.icon(
          onPressed: _busy
              ? null
              : () => _run(l.statusPreparingPrint, l.statusPrinted,
                  () => RoofReport.printReport(_model, labels: l)),
          icon: const Icon(Icons.print),
          label: Text(l.actionPrint),
        ),
        OutlinedButton.icon(
          onPressed: _busy
              ? null
              : () => _run(l.statusBuildingPdf, l.statusSaved,
                  () => RoofReport.saveReport(_model, labels: l, filename: widget.filename)),
          icon: const Icon(Icons.picture_as_pdf),
          label: Text(l.actionSavePdf),
        ),
        OutlinedButton.icon(
          onPressed: _busy
              ? null
              : () => _run(l.statusSharingPdf, l.statusShared,
                  () => RoofReport.shareReport(_model, labels: l, filename: widget.filename)),
          icon: const Icon(Icons.ios_share),
          label: Text(l.actionSharePdf),
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
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final l = widget.labels;
    return LayoutBuilder(builder: (context, constraints) {
      final layout =
          constraints.maxWidth < RoofUiTokens.compactBreakpoint ? ReportLayout.compact : ReportLayout.wide;
      final scenes = _scenesFor(layout);
      final titles = [l.lengthCaption, l.areaCaption, l.summaryPageTitle];
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.showActions) _actions(theme),
          if (widget.showTotals) ...[
            const SizedBox(height: RoofUiTokens.gapLarge),
            RoofTotalsTable(_measurement, labels: l),
          ],
          for (var i = 0; i < scenes.length; i++) ...[
            const SizedBox(height: RoofUiTokens.gapLarge),
            Text(titles[i], style: theme.textTheme.titleMedium),
            const SizedBox(height: RoofUiTokens.gap),
            Semantics(
              image: true,
              label: '${titles[i]}: ${_model.address.display}',
              child: DecoratedBox(
                decoration: BoxDecoration(
                  border: Border.all(color: RoofUiTokens.frame, width: RoofUiTokens.hairline),
                ),
                child: AspectRatio(
                  aspectRatio: scenes[i].width / scenes[i].height,
                  child: RoofDiagramView(scenes[i]),
                ),
              ),
            ),
          ],
        ],
      );
    });
  }
}
