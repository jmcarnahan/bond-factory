import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_capture_link_row.dart';
import 'bond_capture_when.dart';
import 'bond_priority_chip.dart';
import 'task_format.dart';

class _LinkState {
  _LinkState(LinkCandidate l)
      : text = l.text,
        kind = l.kind,
        options = [...l.candidates],
        selected = l.candidates.isEmpty ? -1 : 0;

  final String text;
  final String kind;
  final List<LinkOption> options;

  /// Index into [options], or -1 for no match.
  int selected;

  LinkCandidate? get result {
    if (selected < 0 || selected >= options.length) return null;
    final chosen = options[selected];
    return LinkCandidate(
      text: text,
      kind: kind,
      candidates: [chosen, for (final o in options) if (o != chosen) o],
    );
  }

  LinkCandidate get view => LinkCandidate(text: text, kind: kind, candidates: options);
}

/// One captured item for review: an editable title, a Task / Event switch that
/// converts it, the date and time, the priority (tasks), the mentions with
/// their alternatives (date, time and priority are editable inline; an event
/// has an all-day switch that clears the time; editing a task's date clears
/// its "date guessed" mark), and a mark for low confidence, a guessed date or a
/// missed (past) event. Every edit calls [onChanged] with the item as it now
/// stands: links with no match chosen are left out, and the chosen match comes
/// first among its alternatives. [now] decides "missed"; with none it never shows.
///
/// With [semanticsId]: `<id>-title`, `-kind-task`, `-kind-event`,
/// `-priority-<n>`, `-link-<n>-option-<n>`, `-remove`.
class BondCaptureItemCard extends StatefulWidget {
  const BondCaptureItemCard({
    super.key,
    required this.item,
    required this.onChanged,
    this.onRemove,
    this.linkSearch,
    this.now,
    this.today,
    this.showErrors = false,
    this.labels = const CaptureLabels(),
    this.taskLabels = const TaskLabels(),
    this.semanticsId,
  });

  final CaptureItem item;
  final ValueChanged<CaptureItem> onChanged;
  final VoidCallback? onRemove;
  final LinkSearch? linkSearch;
  final DateTime? now;

  /// The wall date the date field opens on; defaults to [now]'s day, else the item's own date.
  final DateTime? today;

  /// Shows what blocks accepting (an empty title) under the field.
  final bool showErrors;
  final CaptureLabels labels;
  final TaskLabels taskLabels;
  final String? semanticsId;

  @override
  State<BondCaptureItemCard> createState() => _BondCaptureItemCardState();
}

class _BondCaptureItemCardState extends State<BondCaptureItemCard> {
  late final TextEditingController _title;
  late bool _isEvent;
  String? _date;
  String? _time;
  bool _allDay = false;
  bool _defaulted = false;
  String? _endDate;
  String? _endTime;
  TaskPriority? _priority;
  late final List<_LinkState> _links;

  @override
  void initState() {
    super.initState();
    final i = widget.item;
    _title = TextEditingController(text: i.title);
    _links = [for (final l in i.links) _LinkState(l)];
    switch (i) {
      case TaskCandidate():
        _isEvent = false;
        _date = i.dueDate;
        _time = i.dueTime;
        _defaulted = i.dueDefaulted;
        _priority = i.priority;
      case EventCandidate():
        _isEvent = true;
        _date = i.startDate;
        _time = i.startTime;
        _allDay = i.allDay;
        _endDate = i.endDate;
        _endTime = i.endTime;
    }
  }

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  CaptureItem _build() {
    final i = widget.item;
    final links = [
      for (final l in _links) ?l.result,
    ];
    return _isEvent
        ? EventCandidate(
            title: _title.text,
            links: links,
            confidence: i.confidence,
            flags: i.flags,
            degraded: i.degraded,
            startDate: _date,
            startTime: _allDay ? null : _time,
            allDay: _allDay,
            endDate: _endDate,
            endTime: _endTime,
          )
        : TaskCandidate(
            title: _title.text,
            links: links,
            confidence: i.confidence,
            flags: i.flags,
            degraded: i.degraded,
            dueDate: _date,
            dueTime: _time,
            dueDefaulted: _defaulted,
            priority: _priority,
          );
  }

  void _edit(VoidCallback change) {
    setState(change);
    widget.onChanged(_build());
  }

  void _switchTo(String kind) {
    final toEvent = kind == 'event';
    if (toEvent == _isEvent) return;
    _edit(() {
      _isEvent = toEvent;
      if (toEvent) _allDay = _time == null;
    });
  }

  bool get _missed {
    final now = widget.now?.toLocal();
    final d = parseDueDate(_date);
    if (now == null || !_isEvent || d == null) return false;
    final tm = _allDay ? null : parseDueTime(_time);
    if (tm == null) return d.isBefore(DateTime(now.year, now.month, now.day));
    return DateTime(d.year, d.month, d.day, tm.hour24, tm.minute).isBefore(now);
  }

  DateTime get _today {
    final n = widget.now;
    return widget.today ?? (n == null ? (parseDueDate(_date) ?? DateTime(1970)) : DateTime(n.toLocal().year, n.toLocal().month, n.toLocal().day));
  }

  void _setDate(DateTime d) => _edit(() {
        _date = dueDateString(d);
        _defaulted = false;
      });

  void _clearDate() => _edit(() {
        _date = null;
        _time = null;
        _defaulted = false;
      });

  String? _id(String part) => widget.semanticsId == null ? null : '${widget.semanticsId}-$part';

  @override
  Widget build(BuildContext context) {
    final t = BondTokens.of(context);
    final l = widget.labels;
    final low = widget.item.flags.contains('low_confidence') || widget.item.confidence < 0.5;
    final marks = <Widget>[
      if (low || widget.item.degraded) BondStatusChip(BondStatus(l.lowConfidence, tone: BondToneRole.caution)),
      if (!_isEvent && _defaulted) BondStatusChip(BondStatus(l.dateGuessed, tone: BondToneRole.caution)),
      if (_missed) BondStatusChip(BondStatus(l.missed, tone: BondToneRole.danger)),
      if (!_isEvent && _priority != null && _priority != TaskPriority.normal)
        BondPriorityChip(priority: _priority!, labels: widget.taskLabels),
    ];
    return Container(
      padding: BondSpace.all12,
      decoration: BoxDecoration(
        color: t.surface,
        borderRadius: BondRadius.r12All,
        border: Border.all(color: low ? t.caution.soft : t.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: BondTextField(
                  controller: _title,
                  label: l.itemTitle,
                  errorText: widget.showErrors && _title.text.trim().isEmpty ? l.titleRequired : null,
                  onChanged: (_) => _edit(() {}),
                  semanticsId: _id('title'),
                ),
              ),
              if (widget.onRemove != null)
                BondIconButton(
                  icon: Icons.delete_outline,
                  label: l.removeItem,
                  onPressed: widget.onRemove,
                  semanticsId: _id('remove'),
                ),
            ],
          ),
          BondSpace.h8,
          BondSegmented<String>(
            segments: [BondSegment('task', l.asTask), BondSegment('event', l.asEvent)],
            value: _isEvent ? 'event' : 'task',
            onChanged: _switchTo,
            semanticsId: _id('kind'),
          ),
          BondSpace.h12,
          BondCaptureWhen(
            isEvent: _isEvent,
            allDay: _allDay,
            date: _date,
            time: _time,
            today: _today,
            onDate: _setDate,
            onClearDate: _clearDate,
            onTime: (v) => _edit(() => _time = v),
            onAllDay: (v) => _edit(() {
              _allDay = v;
              if (!v && _time == null) _time = '09:00';
            }),
            idOf: _id,
            showTimeNeedsDate: widget.showErrors,
            labels: widget.labels,
            taskLabels: widget.taskLabels,
          ),
          if (marks.isNotEmpty) ...[
            BondSpace.h8,
            Wrap(spacing: BondSpace.s8, runSpacing: BondSpace.s4, children: marks),
          ],
          if (!_isEvent) ...[
            BondSpace.h8,
            BondSegmented<int>(
              segments: [
                BondSegment(0, widget.taskLabels.noPriority),
                for (final p in TaskPriority.values) BondSegment(p.wire, widget.taskLabels.priorityText(p)),
              ],
              value: _priority?.wire ?? 0,
              onChanged: (v) => _edit(() => _priority = TaskPriority.fromWire(v)),
              semanticsId: _id('priority'),
            ),
          ],
          for (var n = 0; n < _links.length; n++) ...[
            BondSpace.h12,
            BondCaptureLinkRow(
              link: _links[n].view,
              selected: _links[n].selected,
              onSelect: (i) => _edit(() => _links[n].selected = i),
              onFound: (o) => _edit(() {
                _links[n].options.add(o);
                _links[n].selected = _links[n].options.length - 1;
              }),
              linkSearch: widget.linkSearch,
              labels: l,
              semanticsId: _id('link-$n'),
            ),
          ],
        ],
      ),
    );
  }
}
