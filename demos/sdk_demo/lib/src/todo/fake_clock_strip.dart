import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../pages/page_scaffold.dart';
import 'todo_services.dart';

/// Fake mode only: a field for an ISO instant and a Tick button. Tick runs
/// `POST /jobs/tick {now}` (the sweep and the delivery as of that instant), then moves the pages'
/// clock there and calls [onTicked] so the page re-reads. Ids: `<id>.clock-now`, `.clock-tick`, `.clock-real`,
/// `.clock-state`, `.clock-error`.
class FakeClockStrip extends StatefulWidget {
  const FakeClockStrip({super.key, required this.services, required this.id, required this.onTicked});

  final TodoServices services;
  final String id;
  final Future<void> Function() onTicked;

  @override
  State<FakeClockStrip> createState() => _FakeClockStripState();
}

class _FakeClockStripState extends State<FakeClockStrip> {
  late final TextEditingController _field = TextEditingController(
    text: widget.services.now().toUtc().toIso8601String(),
  );
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _field.dispose();
    super.dispose();
  }

  Future<void> _real() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.services.realTime();
      _field.text = widget.services.now().toUtc().toIso8601String();
      await widget.onTicked();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _tick() async {
    final at = DateTime.tryParse(_field.text.trim());
    if (at == null) {
      setState(() => _error = 'Enter an ISO instant such as 2026-03-12T16:30:00Z');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.services.tick(at);
      await widget.onTicked();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.services.fakeMode) return const SizedBox.shrink();
    final text = BondText.of(context);
    final tokens = BondTokens.of(context);
    return ValueListenableBuilder<DateTime?>(
      valueListenable: widget.services.fakeNow,
      builder: (context, fake, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Fake clock', style: text.smallStrong),
          BondSpace.h4,
          BondTextField(controller: _field, label: 'Now (ISO instant)', semanticsId: '${widget.id}.clock-now'),
          BondSpace.h8,
          Wrap(
            spacing: BondSpace.s8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              BondButton(
                label: 'Tick',
                variant: BondButtonVariant.secondary,
                loading: _busy,
                onPressed: _busy ? null : _tick,
                semanticsId: '${widget.id}.clock-tick',
              ),
              BondButton(
                label: 'Real time',
                variant: BondButtonVariant.quiet,
                onPressed: _busy ? null : _real,
                semanticsId: '${widget.id}.clock-real',
              ),
              labelledText(
                '${widget.id}.clock-state',
                fake == null ? 'Clock: real time' : 'Clock: ${fake.toIso8601String()}',
                text.caption.copyWith(color: tokens.muted),
              ),
            ],
          ),
          if (_error != null)
            labelledText('${widget.id}.clock-error', _error!, TextStyle(color: tokens.danger.press)),
          BondSpace.h12,
        ],
      ),
    );
  }
}
