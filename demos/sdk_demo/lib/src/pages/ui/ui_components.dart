import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'ui_common.dart';

/// The components section: page-level pieces.
class UiComponents extends StatefulWidget {
  const UiComponents({super.key, required this.say});

  final UiSay say;

  @override
  State<UiComponents> createState() => _UiComponentsState();
}

class _UiComponentsState extends State<UiComponents> {
  int _tab = 0;
  String _variant = 'short';

  @override
  Widget build(BuildContext context) {
    return UiSection(
      id: 'components',
      title: 'Components',
      children: [
        UiTile(
          name: 'page-header',
          selfIdentified: false,
          child: BondPageHeader(
            title: 'Tasks',
            eyebrow: 'Work',
            subtitle: 'Everything due this week',
            breadcrumbs: [BondCrumb('Home', onTap: () {}), const BondCrumb('Tasks')],
            actions: [BondButton(label: 'New', onPressed: () {})],
          ),
        ),
        UiTile(
          name: 'tabs',
          selfIdentified: false,
          child: BondTabs(
            tabs: const [
              BondTab('Open', count: 4, semanticsId: 'sdk.ui.tab-open'),
              BondTab('Done', semanticsId: 'sdk.ui.tab-done'),
            ],
            index: _tab,
            onChanged: (i) => setState(() => _tab = i),
          ),
        ),
        const UiTile(
          name: 'table',
          selfIdentified: false, // the table exposes only its rows (sdk.ui.table-row-<n>), so the tile wears the id
          child: BondTable(
            columns: [BondColumn('Task', flex: 2), BondColumn('Due'), BondColumn('Hours', alignEnd: true)],
            rows: [
              [Text('Order parts'), Text('Mon'), Text('2')],
              [Text('Call supplier'), Text('Tue'), Text('1')],
            ],
            emptyText: 'No rows',
            semanticsId: 'sdk.ui.table',
          ),
        ),
        const UiTile(
          name: 'timeline-list',
          selfIdentified: false,
          child: BondTimelineList(items: [
            BondTimelineItem(timeLabel: '09:00', title: 'Stand-up', body: 'Daily sync'),
            BondTimelineItem(timeLabel: '13:30', title: 'Review', tone: BondToneRole.info),
          ]),
        ),
        UiTile(
          name: 'message-preview',
          child: BondMessagePreview(
            variants: const [
              BondMessageVariant(id: 'short', label: 'Short', body: 'Hi, your order is ready.'),
              BondMessageVariant(id: 'long', label: 'Long', body: 'Hi, your order is ready for pickup today.'),
            ],
            selectedId: _variant,
            onSelected: (id) => setState(() => _variant = id),
            semanticsId: 'sdk.ui.message-preview',
          ),
        ),
        const UiTile(
          name: 'person-chip',
          child: Wrap(spacing: uiGap, runSpacing: uiGap, children: [
            BondPersonChip(label: 'Demo User', slot: 0, semanticsId: 'sdk.ui.person-chip'),
            BondPersonChip(),
          ]),
        ),
        const UiTile(
          name: 'logo-mark',
          selfIdentified: false,
          child: BondLogoMark(logo: Icon(Icons.hub_outlined), size: 32, semanticLabel: 'Logo'),
        ),
        UiTile(
          name: 'stale-banner',
          child: BondStaleBanner(
            asOf: DateTime(2026, 3, 4, 9, 30),
            onRetry: () => widget.say('retry tapped'),
            formatTime: (d) => '09:30',
            semanticsId: 'sdk.ui.stale-banner',
          ),
        ),
        UiTile(
          name: 'email-sign-in',
          child: BondEmailSignIn(
            onSignIn: (email, _) => widget.say('sign in as $email'),
            semanticsId: 'sdk.ui.email-sign-in',
          ),
        ),
        UiTile(
          name: 'google-sign-in',
          child: BondGoogleSignInButton(
            label: 'Continue with Google',
            notice: 'Mock only in the demo.',
            onPressed: () => widget.say('google tapped'),
            semanticsId: 'sdk.ui.google-sign-in',
          ),
        ),
        UiTile(
          name: 'empty-state',
          selfIdentified: false,
          child: BondEmptyState(
            title: 'Nothing here',
            message: 'Add one to get started.',
            actionLabel: 'Add',
            onAction: () => widget.say('add tapped'),
            actionSemanticsId: 'sdk.ui.empty-state-action',
          ),
        ),
        const UiTile(name: 'loading-state', selfIdentified: false, child: BondLoadingState(label: 'Loading')),
        UiTile(
          name: 'error-state',
          child: BondErrorState(
            message: 'Could not load.',
            onRetry: () => widget.say('error retry'),
            semanticsId: 'sdk.ui.error-state',
            retrySemanticsId: 'sdk.ui.error-state-retry',
          ),
        ),
        UiTile(
          name: 'deactivated',
          selfIdentified: false,
          child: SizedBox(
            height: 380,
            child: BondDeactivated(
              title: 'Account deactivated',
              body: 'Ask the owner to turn it back on.',
              signOutLabel: 'Sign out',
              onSignOut: () => widget.say('sign out tapped'),
              signOutSemanticsId: 'sdk.ui.deactivated-sign-out',
            ),
          ),
        ),
        const UiTile(
          name: 'startup-failed',
          selfIdentified: false,
          // A whole MaterialApp of its own, so it gets a fixed box.
          child: SizedBox(
            height: 320,
            child: BondStartupFailed(error: 'Connection refused', baseUrl: 'http://localhost:8012', appName: 'Demo'),
          ),
        ),
      ],
    );
  }
}
