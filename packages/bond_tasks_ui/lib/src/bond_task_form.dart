import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_check_row.dart';
import 'bond_task_checklist_editor.dart';
import 'bond_task_form_due.dart';
import 'bond_task_form_extras.dart';
import 'task_format.dart';

/// A person a task can be assigned to.
class TaskAssignee {
  const TaskAssignee(this.id, this.name);

  final String id;
  final String name;
}

const List<int> _kRemindChoices = [kRemindNone, kRemindUseDefault, kRemindMorningOf, 1, 15, 60, 1440];

/// The full task form: title, notes, date and time, assignee, priority, links
/// (with [onSearchLinks]), checklist, reminder and the calendar mirror switch. Save calls [onSubmit] with a
/// [TaskDraft] only when it is valid; otherwise the problems show inline
/// (a title is required; a time needs a date). An edit passes the task as
/// [initial] and turns the draft into a patch with `TaskPatch.fromDraft`.
///
/// [today] is the person's wall date. With [semanticsPrefix] (say `sdk.tasks`)
/// the elements are `<prefix>.form-title`, `-notes`, `-due-date`, `-due-time`,
/// `-assignee`, `-checklist-add`, `-checklist-item-<n>`, `-reminder`,
/// `-mirror`, `-save` and `-cancel`.
class BondTaskForm extends StatefulWidget {
  const BondTaskForm({
    super.key,
    required this.today,
    required this.onSubmit,
    this.initial,
    this.onCancel,
    this.assignees = const [],
    this.showMirror = true,
    this.busy = false,
    this.labels = const TaskLabels(),
    this.semanticsPrefix,
    this.onSearchLinks,
  });

  final DateTime today;
  final ValueChanged<TaskDraft> onSubmit;
  final Task? initial;
  final VoidCallback? onCancel;
  final List<TaskAssignee> assignees;
  final bool showMirror;
  final bool busy;
  final TaskLabels labels;
  final String? semanticsPrefix;

  /// Searches records to link; with it the form shows the links picker.
  final Future<List<TaskLink>> Function(String kind, String query)? onSearchLinks;

  @override
  State<BondTaskForm> createState() => _BondTaskFormState();
}

class _BondTaskFormState extends State<BondTaskForm> {
  late final TextEditingController _title;
  late final TextEditingController _notes;
  DateTime? _date;
  BondTime? _time;
  String _assignee = '';
  List<ChecklistItem> _checklist = const [];
  int _remind = kRemindUseDefault;
  bool _mirror = true;
  TaskPriority? _priority;
  List<TaskLink> _links = const [];
  bool _tried = false;

  /// False while the time boxes hold something that is not a time; Save waits.
  bool _timeValid = true;

  /// A date or time the server sent that this form cannot read: kept as it
  /// came and sent back unchanged unless the person picks or clears one.
  String? _badDate;
  String? _badTime;

  @override
  void initState() {
    super.initState();
    final t = widget.initial;
    _title = TextEditingController(text: t?.title ?? '');
    _notes = TextEditingController(text: t?.notes ?? '');
    _date = parseDueDate(t?.dueDate);
    _time = parseDueTime(t?.dueTime);
    _badDate = _date == null && (t?.dueDate ?? '').isNotEmpty ? t!.dueDate : null;
    _badTime = _time == null && (t?.dueTime ?? '').isNotEmpty ? t!.dueTime : null;
    _assignee = t?.assignedUserId ?? '';
    _checklist = t?.checklist ?? const [];
    _remind = t?.remindMinutesBefore ?? kRemindUseDefault;
    _mirror = t?.mirrorEnabled ?? true;
    _priority = t?.priority;
    _links = t?.links ?? const [];
  }

  @override
  void dispose() {
    _title.dispose();
    _notes.dispose();
    super.dispose();
  }

  String? _id(String part) => widget.semanticsPrefix == null ? null : '${widget.semanticsPrefix}.form-$part';

  TaskDraft _draft() => TaskDraft(
        title: _title.text,
        notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
        dueDate: _date == null ? _badDate : dueDateString(_date!),
        dueTime: _time == null ? _badTime : dueTimeString(_time!),
        assignedUserId: _assignee.isEmpty ? null : _assignee,
        checklist: _checklist,
        remindMinutesBefore: _remind,
        mirrorEnabled: _mirror,
        links: _links,
        priority: _priority,
      );

  void _save() {
    final draft = _draft();
    setState(() => _tried = true);
    if (draft.validate().isNotEmpty) return;
    widget.onSubmit(draft);
  }

  @override
  Widget build(BuildContext context) {
    final l = widget.labels;
    final problems = _draft().validate();
    final timeNeedsDate = problems.contains(TaskProblem.dueTimeRequiresDate);
    final reminderValues = {..._kRemindChoices, _remind}.toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        BondTextField(
          controller: _title,
          label: l.title,
          maxLength: kTaskTitleMaxLength,
          errorText: problems.contains(TaskProblem.titleTooLong)
              ? l.titleTooLong
              : (_tried && problems.contains(TaskProblem.titleRequired) ? l.titleRequired : null),
          onChanged: (_) => setState(() {}),
          semanticsId: _id('title'),
        ),
        BondSpace.h12,
        BondTextField(controller: _notes, label: l.notes, maxLines: 3, semanticsId: _id('notes')),
        BondSpace.h12,
        BondTaskFormDue(
          labels: l,
          today: widget.today,
          date: _date,
          time: _time,
          badDate: _badDate,
          badTime: _badTime,
          timeNeedsDate: timeNeedsDate,
          onDate: (d) => setState(() {
            _badDate = null;
            _date = d;
          }),
          onClearDate: () => setState(() {
            _badDate = null;
            _date = null;
          }),
          onAddTime: () => setState(() {
            _badTime = null;
            _time = const BondTime(hour24: 9, minute: 0);
          }),
          onTime: (v) => setState(() => _time = v),
          onRemoveTime: () => setState(() {
            _time = null;
            _timeValid = true;
          }),
          onTimeValid: (v) => setState(() => _timeValid = v),
          idOf: _id,
        ),
        if (widget.assignees.isNotEmpty) ...[
          BondSpace.h12,
          BondSelect<String>(
            label: l.assignee,
            variant: BondSelectVariant.expanding,
            value: _assignee,
            options: [
              BondOption('', l.unassigned),
              for (final a in widget.assignees) BondOption(a.id, a.name),
            ],
            onChanged: (v) => setState(() => _assignee = v),
            semanticsId: _id('assignee'),
          ),
        ],
        BondSpace.h12,
        BondTaskFormExtras(
          labels: l,
          priority: _priority,
          onPriority: (v) => setState(() => _priority = v),
          links: _links,
          onLinks: (v) => setState(() => _links = v),
          onSearchLinks: widget.onSearchLinks,
          idOf: _id,
        ),
        BondSpace.h12,
        BondTaskChecklistEditor(
          items: _checklist,
          labels: l,
          semanticsBase: _id('checklist'),
          onChanged: (v) => setState(() => _checklist = v),
        ),
        BondSpace.h12,
        BondSelect<int>(
          label: l.reminder,
          value: _remind,
          options: [for (final v in reminderValues) BondOption(v, l.remindText(v))],
          onChanged: (v) => setState(() => _remind = v),
          semanticsId: _id('reminder'),
        ),
        if (widget.showMirror) ...[
          BondSpace.h8,
          BondCheckRow(
            checked: _mirror,
            label: l.mirror,
            onChanged: (v) => setState(() => _mirror = v),
            semanticsId: _id('mirror'),
          ),
        ],
        BondSpace.h16,
        Row(
          children: [
            BondButton(label: l.save, loading: widget.busy, onPressed: widget.busy || !_timeValid ? null : _save, semanticsId: _id('save')),
            if (widget.onCancel != null) ...[
              BondSpace.w8,
              BondButton(
                label: l.cancel,
                variant: BondButtonVariant.quiet,
                onPressed: widget.onCancel,
                semanticsId: _id('cancel'),
              ),
            ],
          ],
        ),
      ],
    );
  }
}
