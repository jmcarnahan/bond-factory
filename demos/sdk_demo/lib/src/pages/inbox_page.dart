import 'dart:async';

import 'package:bond_notify/bond_notify.dart';
import 'package:bond_notify_ui/bond_notify_ui.dart';
import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../todo/fake_clock_strip.dart';
import '../todo/sync_mirror_notice_feed.dart';
import '../todo/todo_services.dart';
import 'page_scaffold.dart';

enum InboxFeedMode { polling, watch }

/// The inbox over `NoticeController`, with a visible switch between the polling feed
/// (`GET /notices`) and the watch feed (a `WatchNoticeFeed` over an in-memory sync store that this
/// page fills from the same REST data). Row actions go through `POST /notices/{id}/act`; a fresh
/// unread notice raises the browser alert (web). Ids are `sdk.inbox.<element>`: `feed-polling`,
/// `feed-watch`, `feed-state`, `badge`, `list.row-<id>` (+ `-done`, `-snooze`, `-cancel`, `-dismiss`),
/// `list.mark-all`, `list.undo`, `action-state`, `error`, `alerts-permission`, `clock-*`.
class InboxPage extends StatefulWidget {
  const InboxPage({super.key, this.services, this.mode = InboxFeedMode.polling, this.alert, this.pollEvery});

  final TodoServices? services;
  final InboxFeedMode mode;

  /// The browser alert; the default is `browserNoticeAlert()` (a no-op off the web).
  final NoticeAlert? alert;

  /// How often the page asks the feed to refresh; null: every 20 seconds.
  final Duration? pollEvery;

  @override
  State<InboxPage> createState() => _InboxPageState();
}

class _InboxPageState extends State<InboxPage> {
  static const String _id = 'sdk.inbox';

  late final TodoServices _s = widget.services ?? TodoServices.shared;
  late final NoticeAlert _alert = widget.alert ?? browserNoticeAlert();
  late InboxFeedMode _mode = widget.mode;
  NoticeController? _c;
  StreamSubscription<NoticeState>? _sub;
  StreamSubscription<Notice>? _fresh;
  Timer? _poll;
  Timer? _undoClear;
  NoticeState _state = const NoticeState(loading: true);
  String? _undoId;
  String? _undoTask;
  String? _actionState;
  String? _error;
  String _permission = '';
  bool _opened = false;

  /// Bumped by every open and by dispose: an open that finds another number after an await is stale
  /// and builds nothing, so two quick switches leave exactly one controller.
  int _openToken = 0;

  @override
  void initState() {
    super.initState();
    _s.fakeNow.addListener(_clockMoved);
    unawaited(_open());
  }

  @override
  void dispose() {
    _s.fakeNow.removeListener(_clockMoved);
    _poll?.cancel();
    _undoClear?.cancel();
    _openToken++;
    _close();
    super.dispose();
  }

  void _clockMoved() {
    if (mounted) setState(() {});
  }

  void _close() {
    _poll?.cancel();
    _poll = null;
    _sub?.cancel();
    _fresh?.cancel();
    _c?.dispose();
    _c?.feed.dispose();
    _c = null;
  }

  Future<void> _open() async {
    final token = ++_openToken;
    _close();
    _state = const NoticeState(loading: true);
    _error = null;
    if (_c == null && mounted && _opened) setState(() {});
    _opened = true;
    try {
      await _s.signIn();
      await _s.syncClock();
    } catch (e) {
      if (mounted && token == _openToken) {
        setState(() {
          _error = todoErrorText(e);
          _state = const NoticeState();
        });
      }
      return;
    }
    if (!mounted || token != _openToken) return;
    final NoticeFeed feed = _mode == InboxFeedMode.polling
        ? PollingNoticeFeed(_s.notices, clock: _s.now)
        : SyncMirrorNoticeFeed(_s.notices, userId: _s.userId, now: _s.now);
    final c = NoticeController(feed, clock: _s.now);
    _c = c;
    _sub = c.states.listen((s) {
      if (mounted) setState(() => _state = s);
    });
    _fresh = c.newUnread.listen(_alert.show);
    _poll = Timer.periodic(widget.pollEvery ?? const Duration(seconds: 20), (_) => c.refresh());
    await c.start();
  }

  /// How many controllers are open (0 or 1); for tests.
  @visibleForTesting
  bool get hasController => _c != null;

  Future<void> _switch(InboxFeedMode mode) async {
    if (mode == _mode) return;
    setState(() => _mode = mode);
    await _open();
  }

  Future<void> _refresh() async => _c?.refresh();

  Future<void> _act(Notice n, String wire) async {
    setState(() => _error = null);
    try {
      final r = await _s.notices.act(n.id, wire);
      _undoClear?.cancel();
      if (wire == 'done' && mounted) {
        setState(() {
          _undoId = n.id;
          _undoTask = n.taskId;
        });
        _undoClear = Timer(const Duration(seconds: 8), () {
          if (mounted) setState(() => _undoId = null);
        });
      }
      if (mounted) setState(() => _actionState = '${_wordFor(wire)}: ${r.notice.title}');
      await _c?.refresh();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  static String _wordFor(String wire) => switch (wire) {
        'done' => 'Done',
        'snooze' => 'Snoozed',
        'cancel' => 'Cancelled',
        _ => wire,
      };

  Future<void> _undo(Notice n) async {
    final task = _undoTask;
    if (task == null) return;
    try {
      await _s.repo.reopen(task);
      if (mounted) setState(() => _undoId = null);
      await _c?.refresh();
    } catch (e) {
      if (mounted) setState(() => _error = todoErrorText(e));
    }
  }

  Future<void> _allowAlerts() async {
    final ok = await _alert.requestPermission();
    if (mounted) setState(() => _permission = ok ? 'Browser alerts are allowed' : 'Browser alerts are not allowed');
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    final text = BondText.of(context);
    final polling = _mode == InboxFeedMode.polling;
    return DemoScope(
      child: PageFrame(
        title: 'Inbox',
        children: [
          FakeClockStrip(services: _s, id: _id, onTicked: _refresh),
          Row(
            children: [
              Text('Unread', style: text.smallStrong),
              BondSpace.w8,
              BondNoticeBadge(unread: _state.unreadCount, semanticsId: '$_id.badge'),
            ],
          ),
          BondSpace.h8,
          Wrap(
            spacing: BondSpace.s8,
            runSpacing: BondSpace.s8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              BondButton(
                label: 'Polling feed',
                variant: BondButtonVariant.secondary,
                selected: polling,
                onPressed: () => _switch(InboxFeedMode.polling),
                semanticsId: '$_id.feed-polling',
              ),
              BondButton(
                label: 'Watch feed',
                variant: BondButtonVariant.secondary,
                selected: !polling,
                onPressed: () => _switch(InboxFeedMode.watch),
                semanticsId: '$_id.feed-watch',
              ),
              labelledText('$_id.feed-state', polling ? 'Feed: polling' : 'Feed: watch', text.caption),
            ],
          ),
          if (kIsWeb) ...[
            BondSpace.h8,
            BondButton(
              label: 'Allow browser alerts',
              variant: BondButtonVariant.quiet,
              onPressed: _allowAlerts,
              semanticsId: '$_id.alerts-permission',
            ),
            if (_permission.isNotEmpty) labelledText('$_id.alerts-state', _permission, text.caption),
          ],
          BondSpace.h12,
          if (_error != null)
            labelledText('$_id.error', _error!, TextStyle(color: BondTokens.of(context).danger.press)),
          if (_actionState != null) labelledText('$_id.action-state', _actionState!),
          BondSpace.h8,
          BondNoticeList(
            notices: _state.items,
            now: _s.now(),
            loading: _state.loading,
            error: _state.error == null ? null : todoErrorText(_state.error!),
            unreadCount: _state.unreadCount,
            onRetry: _refresh,
            onOpen: (n) => c?.markRead(n.id),
            onAction: _act,
            onDismiss: c == null ? null : (n) => c.dismiss(n.id),
            onMarkAllRead: c?.markAllRead,
            onUndo: _undo,
            undoNoticeId: _undoId,
            semanticsPrefix: '$_id.list',
          ),
        ],
      ),
    );
  }
}
