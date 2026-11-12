import 'package:bond_json/bond_json.dart';
import 'package:test/test.dart';

void main() {
  const rejected = [
    '20260230T101010Z', // basic form, impossible day
    '20260230T101010',
    '20261308T101010Z', // basic form, month 13
    '20261108T241010Z', // basic form, hour 24
    '20261108T106010Z', // basic form, minute 60
    '2026-11-08T25', // hour only
    '2026-11-08T24', // hour only, 24
    '2026-02-30T10', // hour only, impossible day
    '2026-11-08T24:00', // 24:00 is out
    '2026-11-08T23:59:60Z', // leap second is out (it used to read as the next minute)
    '2026-11-08T23:59:60',
  ];

  for (final s in rejected) {
    test('rejects $s', () {
      expect(() => jtime({'t': s}, 't'), throwsA(isA<JsonShapeError>()));
      expect(jtimeOrNull({'t': s}, 't'), isNull);
    });
  }

  test('the same forms still read when they are real', () {
    expect(jtime({'t': '20261108T101010Z'}, 't'), DateTime.utc(2026, 11, 8, 10, 10, 10));
    expect(jtime({'t': '20240229T101010Z'}, 't'), DateTime.utc(2024, 2, 29, 10, 10, 10));
    expect(jtime({'t': '2026-11-08T10'}, 't'), DateTime.utc(2026, 11, 8, 10));
    expect(jtime({'t': '2026-11-08T23:59:59Z'}, 't'), DateTime.utc(2026, 11, 8, 23, 59, 59));
    expect(jtime({'t': '2026-11-08T10:00:00+05:30'}, 't'), DateTime.utc(2026, 11, 8, 4, 30));
  });
}
