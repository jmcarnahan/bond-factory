import 'package:bond_ui/bond_ui.dart';
import 'package:flutter/material.dart';

import 'ui_common.dart';

/// The shell section: navigation and rail pieces.
class UiShell extends StatefulWidget {
  const UiShell({super.key, required this.say});

  final UiSay say;

  @override
  State<UiShell> createState() => _UiShellState();
}

class _UiShellState extends State<UiShell> {
  String _selected = 'home';
  int _bottom = 0;
  bool _accountOpen = false;

  static const _destinations = [
    BondNavDestination(id: 'home', icon: Icons.home_outlined, label: 'Home', semanticsId: 'sdk.ui.nav-home'),
    BondNavDestination(
        id: 'tasks', icon: Icons.check_circle_outline, label: 'Tasks', count: 3, semanticsId: 'sdk.ui.nav-tasks'),
    BondNavDestination(id: 'people', icon: Icons.people_outline, label: 'People', semanticsId: 'sdk.ui.nav-people'),
  ];

  @override
  Widget build(BuildContext context) {
    return UiSection(
      id: 'shell',
      title: 'Shell',
      children: [
        UiTile(
          name: 'side-nav',
          selfIdentified: false,
          child: UiSideScroll(
            child: SizedBox(
              height: 380,
              child: BondSideNav(
                groups: const [BondNavGroup(label: 'Work', items: _destinations)],
                selectedId: _selected,
                onSelected: (id) {
                  setState(() => _selected = id);
                  widget.say('nav $id');
                },
                userCard: BondAccountCard(
                  name: 'Demo User',
                  subtitle: 'demo@example.com',
                  avatar: const BondAvatar(initials: 'DU'),
                  expanded: _accountOpen,
                  onToggle: () => setState(() => _accountOpen = !_accountOpen),
                  actions: [BondAccountRow(icon: Icons.logout, label: 'Sign out', onTap: () {})],
                  semanticsId: 'sdk.ui.account-card',
                ),
                userCardExpanded: _accountOpen,
              ),
            ),
          ),
        ),
        UiTile(
          name: 'nav-tile',
          selfIdentified: false,
          child: UiSideScroll(
            child: SizedBox(
              width: 232,
              child: BondNavTile(
                destination: _destinations[1],
                active: _selected == 'tasks',
                onTap: () => setState(() => _selected = 'tasks'),
              ),
            ),
          ),
        ),
        UiTile(
          name: 'bottom-nav',
          selfIdentified: false,
          child: BondBottomNav(
            items: const [
              BondBottomNavItem(icon: Icons.home_outlined, label: 'Home', semanticsId: 'sdk.ui.bottom-home'),
              BondBottomNavItem(
                  icon: Icons.check_circle_outline, label: 'Tasks', badge: 2, semanticsId: 'sdk.ui.bottom-tasks'),
              BondBottomNavItem(icon: Icons.person_outline, label: 'Me', semanticsId: 'sdk.ui.bottom-me'),
            ],
            currentIndex: _bottom,
            onTap: (i) {
              setState(() => _bottom = i);
              widget.say('bottom nav $i');
            },
          ),
        ),
        const UiTile(
          name: 'rail-card',
          selfIdentified: false,
          child: BondRailCard(title: 'Today', trailing: Text('3 open'), child: Text('Rail cards group side content.')),
        ),
        const UiTile(
          name: 'right-rail',
          selfIdentified: false,
          child: UiSideScroll(
            child: BondRightRail(title: 'Details', width: 300, child: Text('A right rail holds context.')),
          ),
        ),
      ],
    );
  }
}
