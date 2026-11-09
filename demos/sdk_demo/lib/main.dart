import 'package:flutter/material.dart';

void main() => runApp(const SdkDemoApp());

class SdkDemoApp extends StatelessWidget {
  const SdkDemoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'SDK demo',
      home: Scaffold(body: Center(child: Text('sdk_demo'))),
    );
  }
}
