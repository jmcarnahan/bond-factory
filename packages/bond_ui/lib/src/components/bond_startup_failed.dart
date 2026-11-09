import 'package:flutter/material.dart';

import '../theme/theme.dart';
import '../tokens/tokens.dart';
import '../labels.dart';

/// What an app shows when it could not even start (storage, sign-in setup):
/// a plain page in the flow, never a dialog. It carries the error text and the
/// server address so the cause can be read and copied. It is a whole app
/// because nothing else exists yet at that point.
class BondStartupFailed extends StatelessWidget {
  const BondStartupFailed({
    super.key,
    required this.error,
    required this.baseUrl,
    this.appName = 'Bond',
    this.tokens,
  });

  final String error;
  final String baseUrl;
  final String appName;

  /// Tokens for the page; [BondTokens.fallback] when null.
  final BondTokens? tokens;

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: BondTheme.build(tokens ?? BondTokens.fallback),
        home: Builder(builder: (context) {
          final text = BondText.of(context);
          final labels = BondLabels.of(context);
          return Scaffold(
            body: SafeArea(
              child: SingleChildScrollView(
                padding: BondSpace.all24,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(appName, style: text.display),
                    BondSpace.h16,
                    Semantics(
                      identifier: 'startup-failed',
                      header: true,
                      child: Text(labels.startupFailed, key: const ValueKey('startup-failed'), style: text.title),
                    ),
                    BondSpace.h8,
                    Text(labels.startupFailedHint, style: text.body),
                    BondSpace.h16,
                    SelectableText(baseUrl, style: text.small),
                    BondSpace.h8,
                    SelectableText(error, key: const ValueKey('startup-error'), style: text.small),
                  ],
                ),
              ),
            ),
          );
        }),
      );
}
