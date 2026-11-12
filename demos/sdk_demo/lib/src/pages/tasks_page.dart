import 'dart:async';

import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_tasks_ui/bond_tasks_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import '../example_api.dart';
import '../theme.dart';
import 'page_scaffold.dart';
import 'tasks_row_extra.dart';

/// Tasks against the example API: list in sections, quick add, the full form,
/// complete and reopen, checklist ticks, a two-step delete, the calendar mirror
/// result per task, and the fake-clock job run (`POST /jobs/tick`; the notices are on the Inbox page).
/// Ids are `sdk.tasks.<element>`; see `docs/migration/bond_tasks.md` for the
/// list of them.
class TasksPage extends StatefulWidget {
  const TasksPage({super.key, this.api, this.jobs, this.ensureSignedIn, this.clock});

  /// Default: the routes under `/tasks` of the shared demo client.
  final TasksApi? api;

  /// Default: the fake-mode job routes of the shared demo client.
  final DemoJobsApi? jobs;

  /// Default: [DemoSession.ensureSignedIn].
  final Future<Object?> Function()? ensureSignedIn;

  /// The person's clock; the default is the device clock.
  final DateTime Function()? clock;

  @override
  State<TasksPage> createState() => _TasksPageState();
}

class _TasksPageState extends State<TasksPage> {
  static const String _id = 'sdk.tasks';
  static const List<TaskAssignee> _people = [
    TaskAssignee(DemoSession.defaultUserId, 'Demo User'),
    TaskAssignee('demo-user-2', 'Viewer User'),
  ];

  late final TasksApi _api = widget.api ?? TasksApi(DemoSession.api);
  late final DemoJobsApi _jobs = widget.jobs ?? DemoJobsApi(DemoSession.api);

  List<Task>? _tasks;
  TaskSummary? _summary;
  String? _error;
  String? _info;
  bool _busy = false;
  int _formGeneration = 0;

  DateTime get _today {
    final n = (widget.clock ?? DateTime.now)();
    return DateTime(n.year, n.month, n.day);
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      await (widget.ensureSignedIn ?? DemoSession.ensureSignedIn)();
      final today = dueDateString(_today);
      final page = await _api.list(TaskFilters(scope: 'mine', status: 'all', today: today));
      final summary = await _api.summary(today: today);
      if (!mounted) return;
      setState(() {
        _tasks = page.items;
        _summary = summary;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } on AuthFailure catch (e) {
      if (mounted) setState(() => _error = e.message ?? 'Sign-in failed (${e.reason.name})');
    }
  }

  Future<void> _run(Future<void> Function() action, {String? info}) async {
    // A second tap can land before the frame that disables the control: drop it.
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      await action();
      await _load();
      if (mounted && _error == null) setState(() => _info = info);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// The moment the demo ticks the job runner to: two minutes after the latest
  /// open due time, in UTC (a task with no time counts as 23:59), so every
  /// reminder is due.
  static DateTime? tickTime(List<Task> tasks) {
    DateTime? latest;
    for (final t in tasks) {
      if (!t.isOpen) continue;
      final d = parseDueDate(t.dueDate);
      if (d == null) continue;
      final time = parseDueTime(t.dueTime);
      final at = DateTime.utc(d.year, d.month, d.day, time?.hour24 ?? 23, time?.minute ?? 59);
      if (latest == null || at.isAfter(latest)) latest = at;
    }
    return latest?.add(const Duration(minutes: 2));
  }

  Future<void> _runDueJobs() async {
    final at = tickTime(_tasks ?? const []);
    if (at == null) {
      setState(() => _info = 'Add an open task with a due date first.');
      return;
    }
    await _run(() async {
      await _jobs.runDueJobs(at);
    }, info: 'Ran the due jobs as of ${at.toIso8601String()}');
  }

  Widget _extra(BuildContext context, Task t) => TaskRowExtra(
        task: t,
        idPrefix: _id,
        busy: _busy,
        onChecklist: (item, done) => _run(() => _api.setChecklistItem(t.id, item.id, done: done)),
        onMirror: (v) => _run(() async {
          await _api.update(t.id, TaskPatch(mirrorEnabled: v), today: dueDateString(_today));
        }),
        onDelete: () => _run(() => _api.delete(t.id)),
      );

  @override
  Widget build(BuildContext context) {
    final tasks = _tasks;
    return DemoScope(
      child: PageFrame(
        title: 'Tasks',
        children: [
          if (_summary != null) BondTaskSummaryCard(summary: _summary!, semanticsId: '$_id.summary'),
          BondSpace.h12,
          BondTaskQuickAdd(
            semanticsId: '$_id.quick-add',
            enabled: !_busy,
            onSubmit: (title) => _run(() async {
              await _api.create(TaskDraft(title: title), today: dueDateString(_today));
            }),
          ),
          if (_error != null)
            labelledText('$_id.error', _error!, TextStyle(color: BondTokens.of(context).danger.press)),
          if (_info != null) labelledText('$_id.info', _info!),
          BondSpace.h8,
          BondTaskList(
            tasks: _error != null && tasks == null ? null : tasks,
            error: _error != null && tasks == null ? _error : null,
            onRetry: _load,
            today: _today,
            semanticsPrefix: _id,
            // Disabled while a request is in flight: a second tap would re-post
            // (complete, then reopen) and the label changes only after the reload.
            onComplete: _busy
                ? null
                : (t) => _run(() async {
                      await (t.isOpen
                          ? _api.complete(t.id, today: dueDateString(_today))
                          : _api.reopen(t.id, today: dueDateString(_today)));
                    }),
            rowExtra: _extra,
          ),
          BondSpace.h16,
          Wrap(
            spacing: BondSpace.s8,
            runSpacing: BondSpace.s8,
            children: [
              BondButton(
                label: 'Reload',
                variant: BondButtonVariant.secondary,
                onPressed: _busy ? null : _load,
                semanticsId: '$_id.reload',
              ),
              BondButton(
                label: 'Run due jobs',
                variant: BondButtonVariant.secondary,
                onPressed: _busy ? null : _runDueJobs,
                semanticsId: '$_id.run-due-jobs',
              ),
            ],
          ),
          BondSpace.h8,
          const Text('Reminders that were delivered are in the Inbox page.'),
          BondSpace.h24,
          Text('New task', style: BondText.of(context).lead),
          BondSpace.h8,
          BondTaskForm(
            key: ValueKey(_formGeneration),
            today: _today,
            assignees: _people,
            busy: _busy,
            semanticsPrefix: _id,
            onSubmit: (draft) => _run(() async {
              await _api.create(draft, today: dueDateString(_today));
              if (mounted) setState(() => _formGeneration++);
            }),
          ),
        ],
      ),
    );
  }
}
