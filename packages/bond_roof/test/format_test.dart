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

  test('pitchLabel', () {
    expect(pitchLabel(0.19), 'Flat');
    expect(pitchLabel(0.5), 'Flat');
    expect(pitchLabel(0.6), '0.5/12');
    expect(pitchLabel(3.9), '4/12');
    expect(pitchLabel(4.6), '4.5/12');
    expect(pitchLabel(4.2), '4/12');
    expect(pitchLabel(12), '12/12');
  });
}
