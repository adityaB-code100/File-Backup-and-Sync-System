import sys
import os
import unittest

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import phonenumbers
from accounts.location_data import validate_location, SUPPORTED_COUNTRIES, LOCATION_DATA

class TestBackendProfileValidation(unittest.TestCase):

    def test_supported_countries(self):
        self.assertEqual(len(SUPPORTED_COUNTRIES), 4)
        self.assertIn('India', SUPPORTED_COUNTRIES)
        self.assertIn('United States', SUPPORTED_COUNTRIES)
        self.assertIn('United Kingdom', SUPPORTED_COUNTRIES)
        self.assertIn('Canada', SUPPORTED_COUNTRIES)

    def test_location_india_maharashtra_nanded(self):
        valid, err = validate_location('India', 'Maharashtra', 'Nanded')
        self.assertTrue(valid)
        self.assertEqual(err, '')

    def test_location_us_california_san_francisco(self):
        valid, err = validate_location('United States', 'California', 'San Francisco')
        self.assertTrue(valid)
        self.assertEqual(err, '')

    def test_location_uk_england_london(self):
        valid, err = validate_location('United Kingdom', 'England', 'London')
        self.assertTrue(valid)
        self.assertEqual(err, '')

    def test_location_canada_ontario_toronto(self):
        valid, err = validate_location('Canada', 'Ontario', 'Toronto')
        self.assertTrue(valid)
        self.assertEqual(err, '')

    def test_location_empty_is_valid(self):
        valid, err = validate_location('', '', '')
        self.assertTrue(valid)

    def test_location_invalid_country(self):
        valid, err = validate_location('Australia', 'New South Wales', 'Sydney')
        self.assertFalse(valid)
        self.assertIn('not supported', err)

    def test_location_invalid_state_for_country(self):
        valid, err = validate_location('India', 'California', 'Nanded')
        self.assertFalse(valid)
        self.assertIn('not a valid state for India', err)

    def test_location_invalid_city_for_state(self):
        valid, err = validate_location('India', 'Maharashtra', 'Tokyo')
        self.assertFalse(valid)
        self.assertIn('not in the supported location list', err)

    def test_location_city_without_state(self):
        valid, err = validate_location('India', '', 'Nanded')
        self.assertFalse(valid)
        self.assertIn('Cannot select a city without selecting a state', err)

    def test_location_state_without_country(self):
        valid, err = validate_location('', 'Maharashtra', '')
        self.assertFalse(valid)
        self.assertIn('Cannot select a state without selecting a country', err)

    # Phone number validation tests
    def _validate_phone(self, raw_phone):
        if not raw_phone:
            return True, '', ''
        if any(c.isalpha() for c in raw_phone):
            return False, '', 'Mobile number must not contain letters.'
        try:
            parsed = phonenumbers.parse(raw_phone, None)
            if not phonenumbers.is_valid_number(parsed):
                return False, '', 'Invalid mobile number format.'
            if parsed.country_code not in [91, 1, 44]:
                return False, '', 'Phone number must be from supported countries (+91, +1, +44).'
            if parsed.country_code == 91:
                nat_str = str(parsed.national_number)
                if len(nat_str) != 10 or nat_str[0] not in '6789':
                    return False, '', 'Indian mobile number must be 10 digits starting with 6, 7, 8, or 9.'
            e164_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return True, e164_str, ''
        except Exception as e:
            return False, '', str(e)

    def test_phone_india_valid_10_digits(self):
        valid, norm, err = self._validate_phone('+919876543210')
        self.assertTrue(valid)
        self.assertEqual(norm, '+919876543210')

    def test_phone_india_12_digits_rejected(self):
        valid, norm, err = self._validate_phone('+91919876543210')
        self.assertFalse(valid)

    def test_phone_india_fewer_than_10_digits_rejected(self):
        valid, norm, err = self._validate_phone('+9198765')
        self.assertFalse(valid)

    def test_phone_india_starts_with_1_rejected(self):
        valid, norm, err = self._validate_phone('+911234567890')
        self.assertFalse(valid)

    def test_phone_us_valid(self):
        valid, norm, err = self._validate_phone('+14155552671')
        self.assertTrue(valid)
        self.assertEqual(norm, '+14155552671')

    def test_phone_uk_valid(self):
        valid, norm, err = self._validate_phone('+447400123456')
        self.assertTrue(valid)
        self.assertEqual(norm, '+447400123456')

    def test_phone_canada_valid(self):
        valid, norm, err = self._validate_phone('+14165551234')
        self.assertTrue(valid)
        self.assertEqual(norm, '+14165551234')

    def test_phone_letters_rejected(self):
        valid, norm, err = self._validate_phone('+9198765abcde')
        self.assertFalse(valid)

    def test_phone_unsupported_country_rejected(self):
        valid, norm, err = self._validate_phone('+33612345678')
        self.assertFalse(valid)
        self.assertIn('supported countries', err)


if __name__ == '__main__':
    unittest.main()
