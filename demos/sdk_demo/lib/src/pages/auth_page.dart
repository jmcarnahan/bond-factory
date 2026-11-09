import 'package:flutter/widgets.dart';

import 'page_scaffold.dart';

class AuthPage extends StatelessWidget {
  const AuthPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderPage(id: 'auth', title: 'Auth', module: 'bond_auth', phase: 2);
  }
}
