import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'ui_common.dart';

/// The primitives section: every widget of `bond_ui` primitives once.
class UiPrimitives extends StatefulWidget {
  const UiPrimitives({super.key, required this.say});

  final UiSay say;

  @override
  State<UiPrimitives> createState() => _UiPrimitivesState();
}

class _UiPrimitivesState extends State<UiPrimitives> {
  /// A fixed "today" so the calendar never depends on the device clock.
  static final DateTime _today = DateTime(2026, 3, 4);

  final _text = TextEditingController();
  final _search = TextEditingController();
  bool _chip = false;
  bool _acted = false;
  bool _bannerOpen = true;
  int _confirmed = 0;
  String _segment = 'day';
  String? _expanding;
  String _chips = 'a';
  String _radio = 'a';
  String _commit = '15';
  DateTime? _date;
  BondTime _time = const BondTime(hour24: 9, minute: 30);
  String _pressed = 'not pressed';

  static const _options = [BondOption('a', 'Alpha'), BondOption('b', 'Beta'), BondOption('c', 'Gamma')];

  @override
  void dispose() {
    _text.dispose();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return UiSection(
      id: 'primitives',
      title: 'Primitives',
      children: [
        UiTile(
          name: 'button',
          child: Wrap(spacing: uiGap, runSpacing: uiGap, children: [
            BondButton(label: 'Primary', onPressed: () => widget.say('button tapped'), semanticsId: 'sdk.ui.button'),
            BondButton(label: 'Secondary', variant: BondButtonVariant.secondary, onPressed: () {}),
            BondButton(label: 'Strong', variant: BondButtonVariant.strong, onPressed: () {}),
            BondButton(label: 'Quiet', variant: BondButtonVariant.quiet, onPressed: () {}),
            const BondButton(label: 'Disabled', onPressed: null),
            BondButton(label: 'Large', size: BondButtonSize.large, icon: Icons.add, onPressed: () {}),
          ]),
        ),
        UiTile(
          name: 'icon-button',
          child: BondIconButton(
            icon: Icons.refresh,
            label: 'Refresh',
            showLabel: true,
            onPressed: () => widget.say('icon button tapped'),
            semanticsId: 'sdk.ui.icon-button',
          ),
        ),
        UiTile(
          name: 'chip',
          child: Wrap(spacing: uiGap, runSpacing: uiGap, children: [
            BondChip(
              label: 'Open',
              selected: _chip,
              count: 3,
              onTap: () {
                setState(() => _chip = !_chip);
                widget.say(_chip ? 'chip on' : 'chip off');
              },
              semanticsId: 'sdk.ui.chip',
            ),
            const BondChip(label: 'Overdue', tone: BondToneRole.danger, count: 1),
          ]),
        ),
        const UiTile(
          name: 'status-chip',
          child: Wrap(spacing: uiGap, runSpacing: uiGap, children: [
            BondStatusChip(BondStatus('Done', tone: BondToneRole.positive, icon: Icons.check),
                semanticsId: 'sdk.ui.status-chip'),
            BondStatusChip(BondStatus('Waiting', tone: BondToneRole.caution)),
            BondStatusChip(BondStatus('Failed', tone: BondToneRole.danger)),
            BondStatusChip(BondStatus('Plain')),
          ]),
        ),
        const UiTile(
          name: 'avatar',
          selfIdentified: false,
          child: Wrap(spacing: uiGap, children: [BondAvatar(initials: 'DU'), BondAvatar(initials: 'VU', size: 48)]),
        ),
        UiTile(
          name: 'card',
          child: BondCard(
            onTap: () => setState(() => _pressed = 'card tapped'),
            semanticsId: 'sdk.ui.card',
            child: Text('A tappable card ($_pressed)'),
          ),
        ),
        UiTile(
          name: 'pressable',
          child: BondPressable(
            onTap: () => setState(() => _pressed = 'pressable tapped'),
            semanticLabel: 'Pressable region',
            semanticsId: 'sdk.ui.pressable',
            minSize: BondLayout.minTap,
            child: const Padding(padding: EdgeInsets.all(12), child: Text('Press this region')),
          ),
        ),
        const UiTile(
          name: 'dashed-border',
          selfIdentified: false,
          child: BondDashedBorder(child: Padding(padding: EdgeInsets.all(16), child: Text('Drop a file here'))),
        ),
        UiTile(
          name: 'banner',
          child: _bannerOpen
              ? BondBanner(
                  title: 'Heads up',
                  message: 'Banners show state inline.',
                  tone: BondToneRole.caution,
                  actionLabel: 'Details',
                  onAction: () => widget.say('banner action tapped'),
                  onDismiss: () {
                    setState(() => _bannerOpen = false);
                    widget.say('banner dismissed');
                  },
                  dismissLabel: 'Dismiss',
                  stackAction: true,
                  semanticsId: 'sdk.ui.banner',
                )
              : const Text('Banner dismissed'),
        ),
        UiTile(
          name: 'list-row',
          child: Column(children: [
            BondListRow(
              leading: const BondAvatar(initials: 'DU'),
              title: 'Call the supplier',
              subtitle: 'Due today',
              trailing: const BondStatusChip(BondStatus('Open')),
              onTap: () {},
              semanticsId: 'sdk.ui.list-row',
            ),
            const SizedBox(height: uiGap),
            const BondListRow(title: 'Needs someone', subtitle: 'Urgent', urgent: true),
            const SizedBox(height: uiGap),
            const BondListRow(title: 'Finished item', done: true),
          ]),
        ),
        UiTile(
          name: 'action-row',
          child: BondActionRow(
            icon: Icons.notifications_none,
            title: 'Remind the owner',
            contextText: 'Last notified yesterday.',
            actionLabel: 'Remind',
            onAction: () {
              setState(() => _acted = true);
              widget.say('reminder queued');
            },
            result: _acted ? const Text('Reminder queued') : null,
            semanticsId: 'sdk.ui.action-row',
          ),
        ),
        UiTile(
          name: 'confirm',
          child: BondConfirm(
            identity: 'demo',
            semanticsId: 'sdk.ui.confirm',
            trigger: (arm) => BondButton(
              label: 'Send ($_confirmed sent)',
              variant: BondButtonVariant.secondary,
              onPressed: arm,
              // Idle: this is `sdk.ui.confirm`; armed: `sdk.ui.confirm-confirm` and `sdk.ui.confirm-cancel`.
              semanticsId: 'sdk.ui.confirm',
            ),
            onConfirm: () {
              setState(() => _confirmed++);
              widget.say('confirmed ($_confirmed sent)');
            },
            onCancel: () => widget.say('confirm cancelled'),
            undoWindow: const Duration(seconds: 5),
          ),
        ),
        UiTile(
          name: 'segmented',
          selfIdentified: false, // the widget names only its options (<id>-<value>); the tile wears the id
          child: BondSegmented<String>(
            segments: const [BondSegment('day', 'Day'), BondSegment('week', 'Week'), BondSegment('month', 'Month')],
            value: _segment,
            onChanged: (v) {
              setState(() => _segment = v);
              widget.say('segment $v');
            },
            semanticsId: 'sdk.ui.segmented',
          ),
        ),
        UiTile(
          name: 'select',
          child: BondSelect<String>(
            options: const [
              BondOption('a', 'Alpha'),
              BondOption('b', 'Beta'),
              BondOption('c', 'Gamma'),
              BondOption('d', 'Delta'),
            ],
            value: _expanding,
            variant: BondSelectVariant.expanding,
            label: 'Expanding (opens inline)',
            searchable: true,
            onChanged: (v) {
              setState(() => _expanding = v);
              widget.say('select $v');
            },
            semanticsId: 'sdk.ui.select',
          ),
        ),
        UiTile(
          name: 'select-chips',
          selfIdentified: false, // the widget names only its options (<id>-<value>); the tile wears the id
          child: BondSelect<String>(
            options: _options,
            value: _chips,
            label: 'Chips',
            onChanged: (v) {
              setState(() => _chips = v);
              widget.say('chips $v');
            },
            semanticsId: 'sdk.ui.select-chips',
          ),
        ),
        UiTile(
          name: 'select-radio',
          selfIdentified: false, // the widget names only its options (<id>-<value>); the tile wears the id
          child: BondSelect<String>(
            options: _options,
            value: _radio,
            variant: BondSelectVariant.radioList,
            label: 'Radio list',
            onChanged: (v) {
              setState(() => _radio = v);
              widget.say('radio $v');
            },
            semanticsId: 'sdk.ui.select-radio',
          ),
        ),
        UiTile(
          name: 'text-field',
          child: BondTextField(
            controller: _text,
            label: 'Title',
            hint: 'What needs doing?',
            semanticsId: 'sdk.ui.text-field',
          ),
        ),
        UiTile(
          name: 'search-field',
          child: BondSearchField(controller: _search, hint: 'Search', semanticsId: 'sdk.ui.search-field'),
        ),
        UiTile(
          name: 'inline-field',
          child: Row(children: [
            BondInlineField(
              value: _commit,
              width: 96,
              suffix: '%',
              semanticLabel: 'Percent',
              onCommit: (v) => setState(() => _commit = v),
              semanticsId: 'sdk.ui.inline-field',
            ),
            const SizedBox(width: 12),
            Flexible(child: Text('Committed: $_commit')),
          ]),
        ),
        UiTile(
          name: 'date-field',
          child: BondDateField(
            value: _date,
            today: _today,
            label: 'Due date',
            placeholder: 'Pick a date',
            onChanged: (v) {
              setState(() => _date = v);
              widget.say('date picked');
            },
            onCleared: () => setState(() => _date = null),
            semanticsId: 'sdk.ui.date-field',
          ),
        ),
        UiTile(
          name: 'time-field',
          child: BondTimeField(
            value: _time,
            label: 'Start time',
            onChanged: (v) => setState(() => _time = v),
            semanticsId: 'sdk.ui.time-field',
          ),
        ),
        const UiTile(
          name: 'photo',
          selfIdentified: false,
          child: BondPhoto(url: null, width: 160, height: 100, semanticLabel: 'No photo'),
        ),
      ],
    );
  }
}
