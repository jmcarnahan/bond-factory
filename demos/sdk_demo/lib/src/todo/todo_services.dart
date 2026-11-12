import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';
import 'package:bond_notify/bond_notify.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:flutter/foundation.dart';

import '../example_api.dart';
import 'device_zone_io.dart' if (dart.library.js_interop) 'device_zone_web.dart';

/// Finds the records a task can link to through `GET /tasks/links/search`.
class ApiLinkSearch implements LinkSearch {
  const ApiLinkSearch(this.api);

  final TasksApi api;

  @override
  Future<List<TaskLink>> search(String kind, String query) => api.searchLinks(kind, query);
}

/// Everything the TODO pages share: the API clients, the clock (the real one, or the fake one a
/// walk moves with `POST /jobs/tick`), the person's zone and the events the capture page sent on.
///
/// The pages take a [TodoServices] so tests build one over a canned client; the app uses [shared].
class TodoServices {
  TodoServices({
    required this.client,
    this.ensureSignedIn,
    String? userId,
    this.fakeMode = true,
    DateTime Function()? deviceNow,
    String? zone,
    this.eventsPath = '/capture/events',
    this.clockPath = '/fake/clock',
  })  : _userId = userId,
        _deviceNow = deviceNow ?? DateTime.now,
        zone = zone ?? deviceZoneName();

  static TodoServices? _shared;

  /// The services over the demo session. Tests call [resetShared].
  static TodoServices get shared => _shared ??= TodoServices(
        client: DemoSession.api,
        ensureSignedIn: DemoSession.ensureSignedIn,
      );

  static void resetShared() => _shared = null;

  final ApiClient client;

  /// Signs in before the first call; null in tests that need no session.
  final Future<Object?> Function()? ensureSignedIn;
  final String? _userId;

  /// The signed-in person (read when used: the session may start after the services).
  String get userId => _userId ?? DemoSession.session?.userId ?? DemoSession.defaultUserId;

  /// Fake mode shows the clock strip (the example service only).
  final bool fakeMode;
  final DateTime Function() _deviceNow;
  final String eventsPath;
  final String clockPath;

  /// The IANA zone sent with every write (null: the server keeps the stored one).
  String? zone;

  /// The instant the walk moved the clock to; null while the real clock runs.
  final ValueNotifier<DateTime?> fakeNow = ValueNotifier<DateTime?>(null);

  /// Events the capture page sent to the example's event stub, in this session.
  final ValueNotifier<List<EventCandidate>> events = ValueNotifier<List<EventCandidate>>(const []);

  late final TasksApi tasks = TasksApi(client);
  late final TaskSettingsApi settings = TaskSettingsApi(client);
  late final NoticesApi notices = NoticesApi(client);
  late final DemoJobsApi jobs = DemoJobsApi(client);
  late final LinkSearch links = ApiLinkSearch(tasks);
  late final TaskClock taskClock = TaskClock(now);
  late final RemoteTaskRepository repo = RemoteTaskRepository(tasks, clock: taskClock, timeZone: () => zone);

  /// The one "now" of the pages: the fake instant when set, else the device clock.
  DateTime now() => fakeNow.value ?? _deviceNow();

  Future<void> signIn() async {
    await ensureSignedIn?.call();
  }

  /// Pins the server's clock to [instant] (`PUT /fake/clock`), runs the due jobs as of it
  /// (`POST /jobs/tick`), then moves this clock there.
  Future<void> tick(DateTime instant) async {
    final at = instant.toUtc();
    try {
      await client.putJson(clockPath, body: {'now': jiso(at)});
      await jobs.runDueJobs(at);
    } catch (_) {
      // The pin may have landed before the tick failed: show what the server holds, then report.
      await syncClock();
      rethrow;
    }
    fakeNow.value = at;
  }

  /// Un-pins the server's clock (`PUT /fake/clock {now: null}`) and returns to real time.
  Future<void> realTime() async {
    await client.putJson(clockPath, body: {'now': null});
    fakeNow.value = null;
  }

  /// Reads the pinned clock (`GET /fake/clock`) so pages agree with the server. A failure (not
  /// fake mode, no route) leaves the clock as it is.
  Future<void> syncClock() async {
    if (!fakeMode) return;
    try {
      final m = await client.getJson(clockPath);
      final now = jtime(m, 'now');
      fakeNow.value = now?.toUtc();
    } catch (_) {
      // Keep the current clock.
    }
  }

  /// Reads the accepted events back from the service (`GET /capture/events`) into [events].
  Future<void> loadEvents() async {
    try {
      final m = await client.getJson(eventsPath);
      events.value = jlist(m, 'items', (o) => EventCandidate.fromJson(jmapOf(o)));
    } catch (_) {
      // Keep what this session sent.
    }
  }

  /// A draft with the device zone added: the form sends none.
  TaskDraft withZone(TaskDraft d) => TaskDraft(
        title: d.title,
        id: d.id,
        notes: d.notes,
        dueDate: d.dueDate,
        dueTime: d.dueTime,
        assignedUserId: d.assignedUserId,
        checklist: d.checklist,
        remindMinutesBefore: d.remindMinutesBefore,
        mirrorEnabled: d.mirrorEnabled,
        links: d.links,
        source: d.source,
        priority: d.priority,
        dueAt: d.dueAt,
        timeZone: d.timeZone ?? zone,
      );

  /// Sends one accepted event to the example's event stub. The path is `eventsPath`.
  Future<void> sendEvent(EventCandidate e) async {
    await client.postJson(eventsPath, body: {
      'title': e.title,
      'start_date': e.startDate,
      'start_time': e.startTime,
      'all_day': e.allDay,
      'end_date': e.endDate,
      'end_time': e.endTime,
    });
    events.value = [...events.value, e];
  }

  /// The prefs the stage helpers use, from the person's settings.
  static TaskPrefs prefsOf(TaskSettings s) =>
      TaskPrefs(startOfDay: s.startOfDay, endOfDay: s.endOfDay, leadMinutes: s.leadMinutes);
}

/// The words an inline error line shows for [e].
String todoErrorText(Object e) => e is ApiException ? e.message : e.toString();
