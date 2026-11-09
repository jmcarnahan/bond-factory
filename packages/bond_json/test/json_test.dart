import 'package:bond_json/bond_json.dart';
import 'package:test/test.dart';

enum Color { red, green }

void main() {
  group('scalars', () {
    test('jstr', () {
      expect(jstr({'a': 'x'}, 'a'), 'x');
      expect(jstr({}, 'a'), isNull);
      expect(jstr({'a': null}, 'a'), isNull);
      expect(() => jstr({'a': 1}, 'a'), throwsA(isA<JsonShapeError>()));
    });

    test('jint accepts int, num and numeric string', () {
      expect(jint({'a': 3}, 'a'), 3);
      expect(jint({'a': 3.9}, 'a'), 3);
      expect(jint({'a': '42'}, 'a'), 42);
      expect(jint({'a': ' 7 '}, 'a'), 7);
      expect(jint({}, 'a'), isNull);
      expect(() => jint({'a': 'x'}, 'a'), throwsA(isA<JsonShapeError>()));
      expect(() => jint({'a': true}, 'a'), throwsA(isA<JsonShapeError>()));
      expect(() => jint({'a': double.nan}, 'a'), throwsA(isA<JsonShapeError>()));
    });

    test('jnum', () {
      expect(jnum({'a': 1}, 'a'), 1.0);
      expect(jnum({'a': 1.5}, 'a'), 1.5);
      expect(jnum({'a': '2.5'}, 'a'), 2.5);
      expect(jnum({}, 'a'), isNull);
      expect(() => jnum({'a': 'x'}, 'a'), throwsA(isA<JsonShapeError>()));
    });

    test('jbool', () {
      expect(jbool({'a': true}, 'a'), isTrue);
      expect(jbool({}, 'a'), isNull);
      expect(() => jbool({'a': 'true'}, 'a'), throwsA(isA<JsonShapeError>()));
    });

    test('jmap', () {
      expect(jmap({'a': {'b': 1}}, 'a'), {'b': 1});
      expect(jmap({'a': <Object?, Object?>{1: 2}}, 'a'), {'1': 2});
      expect(jmap({}, 'a'), isNull);
      expect(() => jmap({'a': []}, 'a'), throwsA(isA<JsonShapeError>()));
    });
  });

  group('lists', () {
    test('jlist', () {
      expect(jlist({'a': [1, 2]}, 'a', (v) => v as int), [1, 2]);
      expect(jlist({}, 'a', (v) => v as int), isEmpty);
      expect(jlist({'a': null}, 'a', (v) => v as int), isEmpty);
      expect(() => jlist({'a': 'x'}, 'a', (v) => v), throwsA(isA<JsonShapeError>()));
    });

    test('jlist prefixes the element path', () {
      final rows = {
        'items': [
          {'n': 1},
          {'n': 'x'},
        ],
      };
      expect(
        () => jlist(rows, 'items', (v) => jint(v! as Map, 'n')),
        throwsA(isA<JsonShapeError>().having((e) => e.path, 'path', 'items[1].n')),
      );
    });

    test('jlistOf', () {
      expect(jlistOf([1, 2], (v) => v as int), [1, 2]);
      expect(jlistOf(null, (v) => v), isEmpty);
      expect(() => jlistOf({}, (v) => v), throwsA(isA<JsonShapeError>()));
    });
  });

  group('time', () {
    test('Z, offset and naive all end up UTC', () {
      final z = jtime({'t': '2026-11-08T10:30:00Z'}, 't')!;
      final off = jtime({'t': '2026-11-08T12:30:00+02:00'}, 't')!;
      final offNoColon = jtime({'t': '2026-11-08T12:30:00+0200'}, 't')!;
      final naive = jtime({'t': '2026-11-08T10:30:00'}, 't')!;
      final millis = jtime({'t': '2026-11-08T10:30:00.123'}, 't')!;
      for (final t in [z, off, offNoColon, naive]) {
        expect(t.isUtc, isTrue);
        expect(t, DateTime.utc(2026, 11, 8, 10, 30));
      }
      expect(millis, DateTime.utc(2026, 11, 8, 10, 30, 0, 123));
    });

    test('date-only is midnight UTC', () {
      expect(jtime({'t': '2026-11-08'}, 't'), DateTime.utc(2026, 11, 8));
    });

    test('missing, null and empty are null', () {
      expect(jtime({}, 't'), isNull);
      expect(jtime({'t': null}, 't'), isNull);
      expect(jtime({'t': ''}, 't'), isNull);
    });

    test('ints and junk throw', () {
      expect(() => jtime({'t': 1700000000}, 't'), throwsA(isA<JsonShapeError>()));
      expect(() => jtime({'t': 'yesterday'}, 't'), throwsA(isA<JsonShapeError>()));
    });

    test('jiso is UTC, millisecond precision, trailing Z', () {
      expect(jiso(DateTime.utc(2026, 11, 8, 10, 30)), '2026-11-08T10:30:00.000Z');
      expect(jiso(DateTime.utc(2026, 11, 8, 10, 30, 0, 123, 999)), '2026-11-08T10:30:00.123Z');
      expect(jiso(DateTime.parse('2026-11-08T12:30:00+02:00')), '2026-11-08T10:30:00.000Z');
    });

    test('round trip', () {
      final t = DateTime.utc(2026, 1, 2, 3, 4, 5, 678);
      expect(jtime({'t': jiso(t)}, 't'), t);
    });
  });

  group('JsonShapeError', () {
    test('message names path, expected and actual', () {
      try {
        jstr({'name': 5}, 'name');
        fail('should throw');
      } on JsonShapeError catch (e) {
        expect(e.path, 'name');
        expect(e.expected, 'String');
        expect(e.actual, 'int');
        expect(e.toString(), "JsonShapeError: expected String at 'name' but found int");
      }
    });
  });

  group('enumByWire', () {
    String wire(Color c) => c.name.toUpperCase();
    test('known, unknown and null', () {
      expect(enumByWire(Color.values, 'GREEN', wire), Color.green);
      expect(enumByWire(Color.values, 'blue', wire), isNull);
      expect(enumByWire(Color.values, null, wire), isNull);
    });
  });
}
