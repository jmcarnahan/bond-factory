import 'package:bond_tasks/bond_tasks.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'bond_capture_item_card.dart';

class _Entry {
  _Entry(this.n, this.item);

  /// The position the item had in the list given to the review; stable ids.
  final int n;
  CaptureItem item;
}

/// Review what natural-language capture found before anything is created: one
/// [BondCaptureItemCard] per item (edit, switch task or event, remove), a notice
/// line when the parse was [degraded], and Accept / Discard. Accept calls
/// [onAccept] with the items as edited (removed ones are gone). Nothing is
/// created here. [dictation] is a slot the app fills with its own control; [now]
/// marks past events as missed.
///
/// With [semanticsPrefix]: `<prefix>.review-accept`, `-discard`, `-notice`,
/// and cards `<prefix>.review-item-<n>`.
class BondCaptureReview extends StatefulWidget {
  const BondCaptureReview({
    super.key,
    required this.items,
    required this.onAccept,
    required this.onDiscard,
    this.degraded = false,
    this.dropped = 0,
    this.linkSearch,
    this.dictation,
    this.now,
    this.today,
    this.labels = const CaptureLabels(),
    this.taskLabels = const TaskLabels(),
    this.semanticsPrefix,
  });

  final List<CaptureItem> items;
  final bool degraded;

  /// How many items the server discarded (`ParseResult.dropped`); above zero a notice line shows.
  final int dropped;
  final ValueChanged<List<CaptureItem>> onAccept;
  final VoidCallback onDiscard;
  final LinkSearch? linkSearch;
  final Widget? dictation;
  final DateTime? now;
  final DateTime? today;
  final CaptureLabels labels;
  final TaskLabels taskLabels;
  final String? semanticsPrefix;

  @override
  State<BondCaptureReview> createState() => _BondCaptureReviewState();
}

class _BondCaptureReviewState extends State<BondCaptureReview> {
  late List<_Entry> _entries;
  bool _tried = false;

  /// Bumped when new content arrives so the cards start over.
  int _gen = 0;

  @override
  void initState() {
    super.initState();
    _entries = _from(widget.items);
  }

  @override
  void didUpdateWidget(BondCaptureReview old) {
    super.didUpdateWidget(old);
    // A new list with the same content (a parent that rebuilds) keeps the edits.
    if (!_sameContent(old.items, widget.items)) {
      _entries = _from(widget.items);
      _tried = false;
      _gen++;
    }
  }

  static bool _sameContent(List<CaptureItem> a, List<CaptureItem> b) {
    if (identical(a, b)) return true;
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (_key(a[i]) != _key(b[i])) return false;
    }
    return true;
  }

  static String _key(CaptureItem i) => switch (i) {
        TaskCandidate() => 'task|${i.title}|${i.dueDate}|${i.dueTime}|${i.priority?.wire}|${i.dueDefaulted}',
        EventCandidate() => 'event|${i.title}|${i.startDate}|${i.startTime}|${i.allDay}|${i.endDate}|${i.endTime}',
      };

  /// A time needs a date; the card shows the message, Accept waits.
  static bool _timeWithoutDate(CaptureItem i) => switch (i) {
        TaskCandidate() => (i.dueTime ?? '').isNotEmpty && (i.dueDate ?? '').isEmpty,
        EventCandidate() => !i.allDay && (i.startTime ?? '').isNotEmpty && (i.startDate ?? '').isEmpty,
      };

  void _accept() {
    setState(() => _tried = true);
    if (_entries.any((e) => e.item.title.trim().isEmpty || _timeWithoutDate(e.item))) return;
    widget.onAccept([for (final e in _entries) e.item]);
  }

  static List<_Entry> _from(List<CaptureItem> items) => [
        for (var i = 0; i < items.length; i++) _Entry(i, items[i]),
      ];

  String? _id(String part) => widget.semanticsPrefix == null ? null : '${widget.semanticsPrefix}.review-$part';

  @override
  Widget build(BuildContext context) {
    final l = widget.labels;
    final t = BondTokens.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(l.reviewTitle, style: BondText(t).bodyStrong),
        if (widget.dictation != null) ...[BondSpace.h8, widget.dictation!],
        if (widget.degraded) ...[
          BondSpace.h8,
          BondBanner(title: l.degradedNotice, tone: BondToneRole.caution, semanticsId: _id('notice')),
        ],
        if (widget.dropped > 0) ...[
          BondSpace.h8,
          BondBanner(title: l.droppedNotice(widget.dropped), tone: BondToneRole.caution, semanticsId: _id('dropped')),
        ],
        BondSpace.h12,
        if (_entries.isEmpty)
          Text(l.noItems, style: BondText(t).body.copyWith(color: t.muted))
        else
          for (final e in _entries)
            Padding(
              key: ValueKey('capture-entry-$_gen-${e.n}'),
              padding: const EdgeInsets.only(bottom: BondSpace.s12),
              child: BondCaptureItemCard(
                item: e.item,
                onChanged: (v) => e.item = v,
                showErrors: _tried,
                onRemove: () => setState(() => _entries = [
                      for (final k in _entries)
                        if (k != e) k,
                    ]),
                linkSearch: widget.linkSearch,
                now: widget.now,
                today: widget.today,
                labels: l,
                taskLabels: widget.taskLabels,
                semanticsId: _id('item-${e.n}'),
              ),
            ),
        BondSpace.h4,
        Wrap(
          spacing: BondSpace.s8,
          runSpacing: BondSpace.s8,
          children: [
            BondButton(
              label: l.accept,
              onPressed: _entries.isEmpty ? null : _accept,
              semanticsId: _id('accept'),
            ),
            BondButton(
              label: l.discard,
              variant: BondButtonVariant.quiet,
              onPressed: widget.onDiscard,
              semanticsId: _id('discard'),
            ),
          ],
        ),
      ],
    );
  }
}
