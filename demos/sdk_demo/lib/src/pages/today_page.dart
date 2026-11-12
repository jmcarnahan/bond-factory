import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../todo/fake_clock_strip.dart';
import '../todo/todo_alerts.dart';
import '../todo/todo_services.dart';
import 'page_scaffold.dart';

/// The Today view: `GET /tasks/today` through `TaskController`, a stage banner per task at a
/// notice stage (Done, Snooze, Cancel), inline undo after Done, and a by-hand form with priority and
/// links. Ids are `sdk.today.<element>`: `row-<id>`, `complete-<id>`, `section-<name>`,
/// `task-<id>.banner` (+ `-done`, `-snooze`, `-cancel`), `undo`, `form-*`, `error`, `clock-*`.
class TodayPage extends StatefulWidget {
  const TodayPage({super.key, this.services});

  final TodoServices? services;

  @override
  State<TodayPage> createState() => _TodayPageState();
}

class _TodayPageState extends State<TodayPage> {
  static const String _id = 'sdk.today';
  static const List<TaskAssignee> _people = [
    TaskAssignee('demo-user-1', 'Demo User'),
    TaskAssignee('demo-user-2', 'Viewer User'),
  ];

  late final TodoServices _s = widget.services ?? TodoServices.shared;
  late final TaskController _c = TaskController(_s.repo, clock: _s.taskClock);
  late final TaskTicker _ticker = TaskTicker(clock: _s.taskClock);
  StreamSubscription<TaskControllerState>? _sub;
  StreamSubscription<DateTime>? _minutes;
  TaskControllerState _state = const TaskControllerState();
  TaskPrefs _prefs = const TaskPrefs();
  final Set<String> _snoozed = {};
  String? _error;
  bool _busy = false;
  int _formGeneration = 0;

  @override
  void initState() {
    super.initState();
    _sub = _c.states.listen((s) {
      if (mounted) setState(() => _state = s);
    });
    _minutes = _ticker.minutes.listen((_) => _c.refreshDerived());
    _s.fakeNow.addListener(_clockMoved);
    unawaited(_start());
  }

  @override
  void dispose() {
    _s.fakeNow.removeListener(_clockMoved);
    _sub?.cancel();
    _minutes?.cancel();
    _ticker.dispose();
    _c.dispose();
    super.dispose();
  }

  void _clockMoved() {
    _c.refreshDerived();
    if (mounted) setState(() {});
  }

  Future<void> _start() async {
    try {
      await _s.signIn();
      await _s.syncClock();
      await _loadSettings();
      await _c.load();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  Future<void> _loadSettings() async {
    try {
      final settings = await _s.settings.get();
      _s.zone ??= settings.timeZone;
      if (mounted) setState(() => _prefs = TodoServices.prefsOf(settings));
    } catch (_) {
      // The defaults stand; the settings page shows the error.
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _reload() async {
    _snoozed.clear();
    await _loadSettings();
    await _c.load();
  }

  /// The unread inbox notice for [t] at [stage], or null.
  Future<Notice?> _noticeFor(Task t, TaskStage stage) async {
    try {
      final page = await _s.notices.list(limit: 50);
      for (final n in page.items) {
        if (n.taskId == t.id && n.stage == stage.name && n.unread) return n;
      }
    } catch (_) {
      // No notice found: the banner acts on the task directly.
    }
    return null;
  }

  /// Done, Snooze and Cancel go through `POST /notices/{id}/act` when the inbox holds the notice
  /// of this task and stage (so it is marked read, like the inbox row); otherwise on the task.
  Future<void> _bannerAction(Task t, TaskStage stage, NoticeAction a) async {
    final notice = await _noticeFor(t, stage);
    if (notice != null) {
      await _run(() async {
        await _s.notices.act(notice.id, a.wire);
        if (a == NoticeAction.snooze) _snoozed.add('${t.id}|${stage.name}');
        await _c.load();
      });
      return;
    }
    switch (a) {
      case NoticeAction.done:
        unawaited(_c.complete(t.id));
      case NoticeAction.snooze:
        if (mounted) setState(() => _snoozed.add('${t.id}|${stage.name}'));
      case NoticeAction.cancel:
        await _run(() async {
          await _s.repo.cancel(t.id);
          await _c.load();
        });
    }
  }

  List<Widget> _banners(DateTime now) {
    final day = _state.today;
    if (day == null) return const [];
    final out = <Widget>[];
    for (final t in [...day.overdue, ...day.today]) {
      final stage = stageOf(t, _prefs, now, userId: _s.userId);
      if ((stage != TaskStage.close && stage != TaskStage.due && stage != TaskStage.past) ||
          _snoozed.contains('${t.id}|${stage.name}')) {
        continue;
      }
      final last = currentStage(t, _prefs, now, userId: _s.userId)?.last ?? false;
      out.add(Padding(
        padding: const EdgeInsets.only(bottom: BondSpace.s8),
        child: BondStageBanner(
          task: t,
          stage: stage,
          last: last,
          actions: [
            NoticeAction.done,
            NoticeAction.snooze,
            if (t.ownerUserId == _s.userId) NoticeAction.cancel,
          ],
          onAction: (a) => unawaited(_bannerAction(t, stage, a)),
          semanticsPrefix: '$_id.task-${t.id}',
        ),
      ));
    }
    return out;
  }

  /// A tap on a phone notification landed here: say which task it was.
  Widget _opened(String id) {
    final day = _state.today;
    final all = day == null ? const <Task>[] : [...day.overdue, ...day.today, ...day.undated, ...day.doneToday];
    final title = all.where((t) => t.id == id).map((t) => t.title).firstOrNull ?? id;
    return Padding(
      padding: const EdgeInsets.only(bottom: BondSpace.s8),
      child: Row(
        children: [
          Flexible(child: labelledText('$_id.opened', 'Opened from a notification: $title')),
          BondSpace.w8,
          BondButton(
            label: 'Dismiss',
            variant: BondButtonVariant.quiet,
            onPressed: () => TodoAlerts.openedTask.value = null,
            semanticsId: '$_id.opened-dismiss',
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final now = _s.now();
    final day = _state.today;
    final text = BondText.of(context);
    return DemoScope(
      child: PageFrame(
        title: 'Today',
        children: [
          FakeClockStrip(services: _s, id: _id, onTicked: _reload),
          if (_error != null) labelledText('$_id.error', _error!, TextStyle(color: BondTokens.of(context).danger.press)),
          if (_state.error != null)
            labelledText('$_id.load-error', todoErrorText(_state.error!), TextStyle(color: BondTokens.of(context).danger.press)),
          ValueListenableBuilder<String?>(
            valueListenable: TodoAlerts.openedTask,
            builder: (context, id, _) => id == null ? const SizedBox.shrink() : _opened(id),
          ),
          ..._banners(now),
          if (_state.undoTaskId != null)
            Row(
              children: [
                labelledText('$_id.undo-note', 'Marked done'),
                BondSpace.w8,
                BondButton(
                  label: 'Undo',
                  variant: BondButtonVariant.quiet,
                  onPressed: _c.undo,
                  semanticsId: '$_id.undo',
                ),
              ],
            ),
          if (day == null)
            (_error == null && _state.error == null) ? const BondLoadingState() : const SizedBox.shrink()
          else
            BondTodayList(
              today: day,
              now: now,
              semanticsPrefix: _id,
              onComplete: (t) => t.status == TaskStatus.open ? _c.complete(t.id) : _run(() async {
                    await _s.repo.reopen(t.id);
                    await _c.load();
                  }),
            ),
          BondSpace.h24,
          Text('New TODO', style: text.lead),
          BondSpace.h8,
          BondTaskForm(
            key: ValueKey(_formGeneration),
            today: DateTime(now.toLocal().year, now.toLocal().month, now.toLocal().day),
            assignees: _people,
            busy: _busy,
            semanticsPrefix: _id,
            onSearchLinks: _s.links.search,
            onSubmit: (draft) => _run(() async {
              await _s.repo.create(_s.withZone(draft));
              await _c.load();
              if (mounted) setState(() => _formGeneration++);
            }),
          ),
        ],
      ),
    );
  }
}
