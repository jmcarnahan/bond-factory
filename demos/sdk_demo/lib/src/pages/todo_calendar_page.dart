import 'dart:async';

import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../todo/todo_services.dart';
import 'page_scaffold.dart';

/// A month of TODOs: `BondMonthGrid` with a `BondDueMarker` per day and the `BondDueLane` of the
/// selected day. Events sent from the Capture page show under the lane; one in the past reads
/// "Missed" and never "overdue". Ids are `sdk.calendar.<element>`: `grid`, `marker-<yyyy-mm-dd>`,
/// `row-<id>`, `complete-<id>`, `event-<n>`, `clock-state`, `error`.
class TodoCalendarPage extends StatefulWidget {
  const TodoCalendarPage({super.key, this.services});

  final TodoServices? services;

  @override
  State<TodoCalendarPage> createState() => _TodoCalendarPageState();
}

class _TodoCalendarPageState extends State<TodoCalendarPage> {
  static const String _id = 'sdk.calendar';
  static const TaskLabels _labels = TaskLabels();

  late final TodoServices _s = widget.services ?? TodoServices.shared;
  late DateTime _selected = _dayOf(_s.now());
  late DateTime _month = DateTime(_selected.year, _selected.month);
  List<Task> _tasks = const [];

  /// True once the person picked a day or a month: the clock then no longer moves the selection.
  bool _picked = false;
  String? _error;

  static DateTime _dayOf(DateTime instant) {
    final l = instant.toLocal();
    return DateTime(l.year, l.month, l.day);
  }

  @override
  void initState() {
    super.initState();
    _s.fakeNow.addListener(_clockMoved);
    unawaited(_load(sync: true));
  }

  @override
  void dispose() {
    _s.fakeNow.removeListener(_clockMoved);
    super.dispose();
  }

  void _clockMoved() {
    if (!mounted) return;
    setState(() {
      if (!_picked) {
        _selected = _dayOf(_s.now());
        _month = DateTime(_selected.year, _selected.month);
      }
    });
    unawaited(_load());
  }

  Future<void> _load({bool sync = false}) async {
    try {
      await _s.signIn();
      if (sync) await _s.syncClock();
      await _s.loadEvents();
      final out = <Task>[];
      for (var offset = 0;; offset += 200) {
        final page = await _s.repo.list(TaskFilters(scope: 'mine', status: 'open', limit: 200, offset: offset));
        out.addAll(page.items);
        if (page.items.length < 200 || out.length >= page.total) break;
      }
      if (mounted) {
        setState(() {
          _tasks = out;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  List<Task> _on(DateTime day) {
    final key = dueDateString(day);
    return [
      for (final t in _tasks)
        if (dayFor(t, (u) => u.toLocal()) == key) t,
    ];
  }

  Future<void> _complete(Task t) async {
    try {
      await (t.status == TaskStatus.open ? _s.repo.complete(t.id) : _s.repo.reopen(t.id));
      await _load();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  Widget _marker(BuildContext context, DateTime day, DateTime now) {
    final tasks = _on(day);
    return BondDueMarker(
      count: tasks.length,
      overdue: tasks.any((t) => isOverdue(t, now.toUtc())),
      labels: _labels,
      semanticsId: tasks.isEmpty ? null : '$_id.marker-${dueDateString(day)}',
    );
  }

  Widget _events(DateTime now) {
    final key = dueDateString(_selected);
    final text = BondText.of(context);
    return ValueListenableBuilder<List<EventCandidate>>(
      valueListenable: _s.events,
      builder: (context, events, _) {
        final mine = [
          for (final e in events)
            if (e.startDate == key) e,
        ];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var n = 0; n < mine.length; n++)
              labelledText(
                '$_id.event-$n',
                '${mine[n].startTime ?? 'All day'}  ${mine[n].title}'
                '${_missed(mine[n], now) ? '  ${_labels.missed}' : ''}',
                text.body,
              ),
          ],
        );
      },
    );
  }

  /// An event is missed once its start has passed; it is never "overdue".
  bool _missed(EventCandidate e, DateTime now) {
    final d = parseDueDate(e.startDate);
    if (d == null) return false;
    final t = parseDueTime(e.startTime);
    final start = DateTime(d.year, d.month, d.day, t?.hour24 ?? 23, t?.minute ?? 59);
    return start.isBefore(now.toLocal());
  }

  @override
  Widget build(BuildContext context) {
    final now = _s.now();
    final today = _dayOf(now);
    return DemoScope(
      child: PageFrame(
        title: 'Calendar',
        children: [
          if (_error != null)
            labelledText('$_id.error', _error!, TextStyle(color: BondTokens.of(context).danger.press)),
          labelledText(
            '$_id.clock-state',
            _s.fakeNow.value == null
                ? 'Clock: real time (today ${dueDateString(today)})'
                : 'Clock: ${_s.fakeNow.value!.toIso8601String()} (today ${dueDateString(today)})',
            BondText.of(context).caption.copyWith(color: BondTokens.of(context).muted),
          ),
          BondSpace.h8,
          BondMonthGrid(
            visibleMonth: _month,
            selected: _selected,
            today: today,
            semanticsId: '$_id.grid',
            onPrevious: () => setState(() {
              _picked = true;
              _month = DateTime(_month.year, _month.month - 1);
            }),
            onNext: () => setState(() {
              _picked = true;
              _month = DateTime(_month.year, _month.month + 1);
            }),
            onSelect: (d) => setState(() {
              _picked = true;
              _selected = d;
            }),
            isSelectable: (_) => true,
            dayBuilder: (context, day) => _marker(context, day, now),
            daySemantics: (day) {
              final tasks = _on(day);
              return tasks.isEmpty
                  ? ''
                  : _labels.markerText(tasks.length, overdue: tasks.any((t) => isOverdue(t, now.toUtc())));
            },
          ),
          BondSpace.h16,
          BondDueLane(
            tasks: _tasks,
            day: _selected,
            now: now.toUtc(),
            semanticsPrefix: _id,
            onComplete: _complete,
          ),
          BondSpace.h8,
          _events(now),
        ],
      ),
    );
  }
}
