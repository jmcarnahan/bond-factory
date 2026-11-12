import 'package:bond_json/bond_json.dart';
import 'package:test/test.dart';

void main() {
  const impossible = [
    '2026-02-30',
    '2026-02-29',
    '2026-13-01',
    '2026-00-10',
    '2026-04-31',
    '2026-11-00',
    '2026-02-30T10:00:00Z',
    '2026-02-30T10:00:00',
    '2026-11-08T24:00:00Z',
    '2026-11-08T10:61:00Z',
    '2026-11-08T24:61',
    '2026-11-08T10:30:61+02:00',
  ];

  group('jtime rejects impossible calendar dates and times', () {
    for (final s in impossible) {
      test(s, () => expect(() => jtime({'t': s}, 't'), throwsA(isA<JsonShapeError>())));
    }
  });

  group('jtimeOrNull', () {
    test('reads what jtime reads', () {
      expect(jtimeOrNull({'t': '2026-11-08T10:30:00Z'}, 't'), DateTime.utc(2026, 11, 8, 10, 30));
      expect(jtimeOrNull({'t': '2026-11-08T12:30:00+02:00'}, 't'), DateTime.utc(2026, 11, 8, 10, 30));
      expect(jtimeOrNull({'t': '2026-11-08T10:30:00'}, 't'), DateTime.utc(2026, 11, 8, 10, 30));
      expect(jtimeOrNull({'t': '2026-11-08'}, 't'), DateTime.utc(2026, 11, 8));
    });
    test('missing, null, empty, non-string and junk are null', () {
      expect(jtimeOrNull({}, 't'), isNull);
      expect(jtimeOrNull({'t': null}, 't'), isNull);
      expect(jtimeOrNull({'t': '  '}, 't'), isNull);
      expect(jtimeOrNull({'t': 1700000000}, 't'), isNull);
      expect(jtimeOrNull({'t': 'yesterday'}, 't'), isNull);
    });
    for (final s in impossible) {
      test('null for $s', () => expect(jtimeOrNull({'t': s}, 't'), isNull));
    }
  });

  group('valid edge dates still read', () {
    test('leap days', () {
      expect(jtime({'t': '2028-02-29'}, 't'), DateTime.utc(2028, 2, 29));
      expect(jtime({'t': '2000-02-29T23:59:59Z'}, 't'), DateTime.utc(2000, 2, 29, 23, 59, 59));
      expect(jtimeOrNull({'t': '2028-02-29T00:00:00'}, 't'), DateTime.utc(2028, 2, 29));
    });
    test('month and day ends, hour 23, minute and second 59', () {
      expect(jtime({'t': '2026-12-31T23:59:59Z'}, 't'), DateTime.utc(2026, 12, 31, 23, 59, 59));
      expect(jtime({'t': '2026-04-30'}, 't'), DateTime.utc(2026, 4, 30));
      expect(jtime({'t': '2026-01-01T00:00:00'}, 't'), DateTime.utc(2026, 1, 1));
    });
    test('a century year that is not a leap year', () {
      expect(() => jtime({'t': '1900-02-29'}, 't'), throwsA(isA<JsonShapeError>()));
    });
  });
}
