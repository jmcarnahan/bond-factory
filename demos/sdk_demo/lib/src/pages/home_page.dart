import 'package:flutter/material.dart';

import '../pages.dart';
import 'page_scaffold.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return PageFrame(
      title: 'Home',
      children: [
        const Text('One route per SDK module. Each shows its state inline.'),
        const SizedBox(height: 8),
        for (final page in demoPages)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Semantics(
              identifier: 'sdk.home.route-${page.id}',
              child: Text('${page.path}  ${page.module}  phase ${page.phase}'),
            ),
          ),
      ],
    );
  }
}
