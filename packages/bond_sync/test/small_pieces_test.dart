import 'package:bond_sync/bond_sync.dart';
import 'package:test/test.dart';

void main() {
  group('kVerdictText', () {
    test('has words for every base code', () {
      for (final c in [
        'invalid',
        'invalid_phone',
        'unsupported',
        'not_found',
        'forbidden',
        'conflict',
        'server_error',
        'already',
        'rate_limited',
      ]) {
        expect(kVerdictText[c], isNotEmpty, reason: c);
      }
    });

    test('verdictText prefers the table, then the server message, then a generic line', () {
      expect(verdictText('forbidden'), kVerdictText['forbidden']);
      expect(verdictText('app_code', message: ' Custom '), 'Custom');
      expect(verdictText('app_code'), kVerdictText['server_error']);
      expect(verdictText('app_code', texts: {...kVerdictText, 'app_code': 'mine'}), 'mine');
    });
  });

  group('names', () {
    test('defaults and an app override', () {
      const d = BondSyncNames();
      expect(d.prefix, 'bond');
      expect(d.loggerName, 'bond.sync');
      expect(const BondSyncNames(prefix: 'crm', loggerName: 'crm.sync').dbPath('/data', 'u1'), '/data/crm_u1.db');
    });

    test('syncDbPath cleans the user id and handles separators', () {
      expect(syncDbPath('/data', 'a@b/c'), '/data/bond_a_b_c.db');
      expect(syncDbPath('/data/', 'u'), '/data/bond_u.db');
      expect(syncDbPath(r'C:\data', 'u', prefix: 'x'), r'C:\data\x_u.db');
    });
  });

  group('ServerClock', () {
    test('note records the offset and tells the host', () {
      var phone = DateTime.utc(2026, 11, 8, 10);
      Duration? told;
      final c = ServerClock(() => phone, Duration.zero, (o) => told = o);
      c.note(DateTime.utc(2026, 11, 8, 10, 0, 30));
      expect(c.offset, const Duration(seconds: 30));
      expect(c.skew, const Duration(seconds: 30));
      expect(told, const Duration(seconds: 30));
      phone = phone.add(const Duration(minutes: 1));
      expect(c.now(), DateTime.utc(2026, 11, 8, 10, 1, 30));
      expect(c.phoneNow(), phone);
    });

    test('restore sets the offset without telling the host', () {
      var called = false;
      final c = ServerClock(DateTime.now, Duration.zero, (_) => called = true)..restore(const Duration(seconds: 5));
      expect(c.offset, const Duration(seconds: 5));
      expect(called, isFalse);
    });
  });

  group('ids', () {
    test('newId is a version 4 uuid and unique', () {
      final a = newId();
      expect(a, matches(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')));
      expect(newId(), isNot(a));
    });

    test('actionOf and isoOf', () {
      expect(actionOf('complete'), '{"action":"complete"}');
      expect(isoOf(DateTime.utc(2026, 1, 2)), '2026-01-02T00:00:00.000Z');
    });
  });

  group('SyncSummary', () {
    test('rejections need attention and beat everything', () {
      final s = SyncSummary.of(rejected: 1, queued: 2, connected: true, uploading: true);
      expect(s.needsAttention, isTrue);
      expect(s.sending, isTrue);
      expect(s.isQuiet, isFalse);
    });

    test('offline with queued writes, failing, quiet', () {
      expect(SyncSummary.of(rejected: 0, queued: 1, connected: false).offlineQueued, isTrue);
      expect(SyncSummary.of(rejected: 0, queued: 1, connected: true, uploadFailing: true).failing, isTrue);
      expect(SyncSummary.of(rejected: 0, queued: 0, connected: true).isQuiet, isTrue);
    });

    test('not connected needs a past sync or a download error, and equality holds', () {
      expect(SyncSummary.of(rejected: 0, queued: 0, connected: false).notConnected, isFalse);
      expect(
        SyncSummary.of(rejected: 0, queued: 0, connected: false, lastSynced: DateTime.utc(2026)).notConnected,
        isTrue,
      );
      expect(SyncSummary.of(rejected: 0, queued: 0, connected: true, downloadError: true).notConnected, isTrue);
      expect(const SyncSummary(rejected: 1), const SyncSummary(rejected: 1));
      expect(const SyncSummary(rejected: 1).hashCode, const SyncSummary(rejected: 1).hashCode);
    });
  });

  test('UploadLimits defaults are the contract numbers', () {
    const l = UploadLimits();
    expect(l.chunkSize, 100);
    expect(l.chunkBytes, 512 * 1024);
    expect(l.transientMaxCount, 8);
    expect(l.transientMaxSpan, const Duration(minutes: 15));
    expect(l.transientStale, const Duration(minutes: 10));
  });
}
