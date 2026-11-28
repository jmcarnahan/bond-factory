import 'package:bond_roof/bond_roof.dart';
import 'package:test/test.dart';

void main() {
  test('feetInches', () {
    expect(feetInches(209.67), '209ft 8in');
    expect(feetInches(0), '0ft 0in');
    expect(feetInches(11.99), '12ft 0in');
    expect(feetInches(35), '35ft 0in');
    expect(feetInches(0.04), '0ft 0in');
    expect(feetInches(0.05), '0ft 1in');
    expect(feetInches(1234.5), '1234ft 6in');
    expect(feetInches(double.nan), '0ft 0in');
  });

  test('wholeFeet', () {
    expect(wholeFeet(35.4), '35');
    expect(wholeFeet(35.5), '36');
    expect(wholeFeet(0.2), '0');
  });

  test('sqft', () {
    expect(sqft(2121.4), '2,121');
    expect(sqft(999.5), '1,000');
    expect(sqft(0), '0');
    expect(sqft(12345678.2), '12,345,678');
    expect(sqft(100), '100');
    expect(sqft(1000), '1,000');
  });

  group('pitchLabel: the whole number (half up), the fit beside it when it differs at the tenth', () {
    test('the examples of the contract', () {
      expect(pitchLabel(4.31), '4/12 (4.3)');
      expect(pitchLabel(5.0), '5/12');
    });

    test('a fit within 0.05 of the whole number shows only the whole number', () {
      expect(pitchLabel(4.04), '4/12');
      expect(pitchLabel(3.96), '4/12');
      expect(pitchLabel(6.02), '6/12');
      expect(pitchLabel(12), '12/12');
    });

    test('0.05 or more away shows the fit', () {
      expect(pitchLabel(4.06), '4/12 (4.1)');
      expect(pitchLabel(3.94), '4/12 (3.9)');
      expect(pitchLabel(5.89), '6/12 (5.9)');
    });

    test('the whole number rounds half up', () {
      expect(pitchLabel(4.5), '5/12 (4.5)');
      expect(pitchLabel(4.49), '4/12 (4.5)');
      expect(pitchLabel(7.5), '8/12 (7.5)');
    });

    test('a rise that is not a pitch never throws: it reads as flat', () {
      for (final v in [double.infinity, double.negativeInfinity, double.nan, 1e300]) {
        expect(pitchLabel(v), 'Flat', reason: '$v');
      }
    });

    test('flat is a rise of half a unit or less; the word is a label', () {
      expect(pitchLabel(0.19), 'Flat');
      expect(pitchLabel(0.5), 'Flat');
      expect(pitchLabel(0.6), '1/12 (0.6)');
      expect(pitchLabel(0.2, labels: RoofLabels.fromMap({'pitch_flat': 'Plano'})), 'Plano');
    });
  });
}
