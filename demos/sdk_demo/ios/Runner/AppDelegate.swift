import Flutter
import UIKit
import UserNotifications

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Local notifications (flutter_local_notifications) and push (the `push` plugin) both take the
    // notification-center delegate: set it BEFORE the plugins register so taps and the Done / Snooze /
    // Cancel buttons of a local notification still arrive (see packages/bond_push/README.md).
    // The `push` plugin needs no further Swift on iOS: it hands the Apple token to Dart by itself.
    UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  }
}
