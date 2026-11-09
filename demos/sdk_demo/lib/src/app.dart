import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'errors.dart';
import 'pages.dart';
import 'theme.dart';

GoRouter buildDemoRouter({String initialLocation = '/'}) {
  return GoRouter(
    initialLocation: initialLocation,
    routes: [
      ShellRoute(
        builder: (context, state, child) => DemoShell(location: state.uri.path, child: child),
        routes: [
          for (final page in demoPages)
            GoRoute(
              path: page.path,
              pageBuilder: (context, state) => NoTransitionPage<void>(
                key: state.pageKey,
                child: page.builder(context),
              ),
            ),
        ],
      ),
    ],
  );
}

class SdkDemoApp extends StatefulWidget {
  const SdkDemoApp({super.key, this.initialLocation = '/'});

  final String initialLocation;

  @override
  State<SdkDemoApp> createState() => _SdkDemoAppState();
}

class _SdkDemoAppState extends State<SdkDemoApp> {
  late final GoRouter _router = buildDemoRouter(initialLocation: widget.initialLocation);

  @override
  void dispose() {
    _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'SDK demo',
      theme: buildDemoTheme(),
      routerConfig: _router,
    );
  }
}

/// Left navigation plus the current page. No drawer, no overlays.
class DemoShell extends StatelessWidget {
  const DemoShell({super.key, required this.location, required this.child});

  final String location;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            const _ErrorStrip(),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final narrow = constraints.maxWidth < 600;
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SizedBox(
                        width: narrow ? 120 : 200,
                        child: _Nav(location: location),
                      ),
                      const VerticalDivider(width: 1),
                      Expanded(child: child),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Nav extends StatelessWidget {
  const _Nav({required this.location});

  final String location;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        for (final page in demoPages)
          Semantics(
            identifier: 'sdk.nav.${page.id}',
            child: ListTile(
              dense: true,
              selected: location == page.path,
              title: Text(page.title),
              onTap: () => context.go(page.path),
            ),
          ),
      ],
    );
  }
}

class _ErrorStrip extends StatelessWidget {
  const _ErrorStrip();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ValueListenableBuilder<List<String>>(
      valueListenable: DemoErrors.instance,
      builder: (context, errors, _) {
        if (errors.isEmpty) return const SizedBox.shrink();
        return Semantics(
          identifier: 'sdk.errors',
          container: true,
          child: Container(
            width: double.infinity,
            color: scheme.errorContainer,
            padding: const EdgeInsets.all(8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  identifier: 'sdk.errors.count',
                  container: true,
                  child: Text(
                    'Runtime errors: ${errors.length}',
                    style: TextStyle(color: scheme.onErrorContainer, fontWeight: FontWeight.bold),
                  ),
                ),
                // Newest first; the full list is capped at DemoErrors.maxEntries.
                for (final message in errors.take(3))
                  Text(
                    message,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: scheme.onErrorContainer),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
