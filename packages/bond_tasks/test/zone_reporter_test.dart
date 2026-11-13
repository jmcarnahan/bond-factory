import 'dart:convert';

import 'package:bond_api/bond_api.dart';
import 'package:bond_tasks/bond_tasks.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:test/test.dart';

class _Source implements TimeZoneSource {
  String? zone;
  @override
  Future<String?> currentZone() async => zone;
}

class _Rig {
  _Rig({this.stored}) {
    reporter = ZoneReporter(
      source,
      TaskSettingsApi(ApiClient(baseUrl: Uri.parse('https://api.test/v1'), http: MockClient(_answer))),
    );
  }

  String? stored;
  bool failPut = false;
  final source = _Source();
  final List<http.Request> seen = [];
  late final ZoneReporter reporter;

  Future<http.Response> _answer(http.Request r) async {
    seen.add(r);
    if (r.method == 'PUT' && failPut) return http.Response('{}', 500, headers: {'content-type': 'application/json'});
    return http.Response(jsonEncode({'time_zone': stored}), 200, headers: {'content-type': 'application/json'});
  }

  List<Object?> get puts => [for (final r in seen.where((r) => r.method == 'PUT')) jsonDecode(r.body)];
  int get gets => seen.where((r) => r.method == 'GET').length;
}

void main() {
  test('sends the zone once and not again while it is unchanged', () async {
    final r = _Rig()..source.zone = 'America/Denver';
    await r.reporter.reportIfChanged();
    await r.reporter.reportIfChanged();
    expect(r.puts, [
      {'time_zone': 'America/Denver'}
    ]);
    expect(r.gets, 1, reason: 'the stored zone is read once, to seed');
  });

  test('sends again after the zone changes', () async {
    final r = _Rig()..source.zone = 'America/Denver';
    await r.reporter.reportIfChanged();
    r.source.zone = 'America/New_York';
    await r.reporter.reportIfChanged();
    expect(r.puts.length, 2);
    expect(r.puts.last, {'time_zone': 'America/New_York'});
  });

  test('a zone the server already has is not sent', () async {
    final r = _Rig(stored: 'America/Denver')..source.zone = 'America/Denver';
    await r.reporter.reportIfChanged();
    expect(r.puts, isEmpty);
  });

  test('a failed send leaves the last value alone so the next call retries', () async {
    final r = _Rig()..source.zone = 'America/Denver';
    r.failPut = true;
    await r.reporter.reportIfChanged();
    expect(r.puts.length, 1);
    r.failPut = false;
    await r.reporter.reportIfChanged();
    expect(r.puts.length, 2);
    await r.reporter.reportIfChanged();
    expect(r.puts.length, 2);
  });

  test('an unknown zone sends nothing', () async {
    final r = _Rig();
    await r.reporter.reportIfChanged();
    expect(r.seen, isEmpty);
  });

  test('reports the zone through a store that is not the HTTP api', () async {
    final store = _FakeStore();
    final source = _Source()..zone = 'America/Denver';
    await ZoneReporter(source, store).reportIfChanged();
    expect(store.patches.map((p) => p.timeZone), ['America/Denver']);
  });
}

class _FakeStore implements TaskSettingsStore {
  final List<TaskSettingsPatch> patches = [];
  @override
  Future<TaskSettings> get() async => TaskSettings.fromJson(const {});
  @override
  Future<TaskSettings> update(TaskSettingsPatch p) async {
    patches.add(p);
    return TaskSettings.fromJson(const {});
  }
}
