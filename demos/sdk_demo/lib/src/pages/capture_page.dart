import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../todo/todo_services.dart';
import 'page_scaffold.dart';

/// Natural-language capture: type a phrase, `POST /tasks/parse`, review the drafts (flip task and
/// event, edit date, time, priority, link), accept. Tasks are created through the repository; events
/// go to the example's event stub. Ids are `sdk.capture.<element>`: `text`, `parse`, `error`,
/// `result`, and the review's `review-accept`, `review-discard`, `review-notice`, `review-item-<n>`.
class CapturePage extends StatefulWidget {
  const CapturePage({super.key, this.services});

  final TodoServices? services;

  @override
  State<CapturePage> createState() => _CapturePageState();
}

class _CapturePageState extends State<CapturePage> {
  static const String _id = 'sdk.capture';

  late final TodoServices _s = widget.services ?? TodoServices.shared;
  final TextEditingController _text = TextEditingController();
  ParseResult? _parsed;
  String? _error;
  String? _result;
  bool _busy = false;
  bool _modelDown = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  DateTime get _now => _s.now();

  String get _today {
    final l = _now.toLocal();
    return dueDateString(DateTime(l.year, l.month, l.day));
  }

  Future<void> _setModel(bool down) async {
    setState(() => _error = null);
    try {
      await _s.signIn();
      await _s.client.putJson('/fake/capture', body: {'down': down});
      if (mounted) setState(() => _modelDown = down);
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  Future<void> _parse() async {
    final text = _text.text.trim();
    if (text.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
      _parsed = null; // an old review must not stay under a new outcome
    });
    try {
      await _s.signIn();
      final r = await _s.tasks.parse(text, timeZone: _s.zone);
      if (mounted) setState(() => _parsed = r);
    } catch (e) {
      final denied = e is ServerError && (e.code == 'capture_denied' || e.statusCode == 429);
      if (mounted) setState(() => _error = denied ? const CaptureLabels().captureDenied : todoErrorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _accept(List<CaptureItem> items) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    var tasks = 0, events = 0;
    try {
      for (final i in items) {
        switch (i) {
          case TaskCandidate():
            final links = [
              for (final l in i.links)
                if (l.candidates.isNotEmpty)
                  TaskLink(kind: l.kind, id: l.candidates.first.id, label: l.candidates.first.label),
            ];
            await _s.repo.create(_s.withZone(i.toDraft(links: links)));
            tasks++;
          case EventCandidate():
            await _s.sendEvent(i);
            events++;
        }
      }
      if (mounted) {
        setState(() {
          _parsed = null;
          _text.clear();
          _result = 'Created $tasks ${tasks == 1 ? 'task' : 'tasks'} and sent $events ${events == 1 ? 'event' : 'events'}';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Created $tasks, then stopped: ${todoErrorText(e)}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final parsed = _parsed;
    final danger = TextStyle(color: BondTokens.of(context).danger.press);
    return DemoScope(
      child: PageFrame(
        title: 'Capture',
        children: [
          BondTextField(
            controller: _text,
            label: 'What do you need to do?',
            maxLines: 3,
            maxLength: 500,
            semanticsId: '$_id.text',
          ),
          BondSpace.h8,
          BondButton(
            label: 'Find tasks and events',
            loading: _busy && parsed == null,
            onPressed: _busy ? null : _parse,
            semanticsId: '$_id.parse',
          ),
          if (_s.fakeMode) ...[
            BondSpace.h8,
            BondCheckRow(
              checked: _modelDown,
              label: 'Switch the model off (fake mode)',
              onChanged: _setModel,
              semanticsId: '$_id.model-off',
            ),
          ],
          if (_error != null) labelledText('$_id.error', _error!, danger),
          if (_result != null) labelledText('$_id.result', _result!),
          if (parsed != null) ...[
            BondSpace.h16,
            BondCaptureReview(
              items: parsed.items,
              degraded: parsed.degraded,
              dropped: parsed.dropped,
              linkSearch: _s.links,
              now: _now,
              today: parseDueDate(_today),
              onAccept: _accept,
              onDiscard: () => setState(() => _parsed = null),
              semanticsPrefix: _id,
            ),
          ],
          BondSpace.h16,
          ValueListenableBuilder<List<EventCandidate>>(
            valueListenable: _s.events,
            builder: (context, sent, _) => labelledText('$_id.events-sent', 'Events sent: ${sent.length}'),
          ),
        ],
      ),
    );
  }
}
