import 'package:flutter/material.dart';

import 'src/demo_page.dart';
import 'src/tokens.dart';

void main() => runApp(const RoofDemoApp());

class RoofDemoApp extends StatelessWidget {
  const RoofDemoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Roof demo',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: DemoTokens.seed),
        useMaterial3: true,
      ),
      home: const DemoPage(),
    );
  }
}
