import {
  parseStoredMobile,
  validateNationalNumber,
  getNormalizedE164,
  formatDisplayMobile
} from '../frontend/src/utils/phoneUtils.js';

import {
  SUPPORTED_COUNTRIES,
  DIAL_COUNTRIES,
  LOCATION_DATA
} from '../frontend/src/data/locations.js';

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    passed++;
    console.log(`  ✓ ${message}`);
  } else {
    failed++;
    console.error(`  ✗ FAIL: ${message}`);
  }
}

console.log('\n--- 1. Testing Mobile Number Parsing & Formatting ---');
// India
const parsedIn = parseStoredMobile('+919876543210');
assert(parsedIn.countryCode === 'IN', 'Parses +91 to countryCode IN');
assert(parsedIn.nationalNumber === '9876543210', 'Parses national number 9876543210');
assert(formatDisplayMobile('+919876543210') === '🇮🇳 +91 9876543210', 'Formatted display mobile matches 🇮🇳 +91 9876543210');

// US
const parsedUs = parseStoredMobile('+14155552671');
assert(parsedUs.countryCode === 'US', 'Parses +14155552671 to countryCode US');
assert(parsedUs.nationalNumber === '4155552671', 'Parses national number 4155552671');

// UK
const parsedUk = parseStoredMobile('+447911123456');
assert(parsedUk.countryCode === 'GB', 'Parses +447911123456 to countryCode GB');
assert(parsedUk.nationalNumber === '7911123456', 'Parses national number 7911123456');

// Canada
const parsedCa = parseStoredMobile('+14165551234');
assert(parsedCa.countryCode === 'CA', 'Parses +14165551234 to countryCode CA');
assert(parsedCa.nationalNumber === '4165551234', 'Parses national number 4165551234');

// Unparseable / non-standard number does not crash or erase
const parsedRaw = parseStoredMobile('unknown123');
assert(parsedRaw.nationalNumber === 'unknown123', 'Unparseable number preserves raw value for correction');

console.log('\n--- 2. Testing Mobile Number Validation (Frontend) ---');
// India validations
assert(validateNationalNumber('9876543210', 'IN') === '', 'India 10-digit starting with 9 is valid');
assert(validateNationalNumber('8123456789', 'IN') === '', 'India 10-digit starting with 8 is valid');
assert(validateNationalNumber('7123456789', 'IN') === '', 'India 10-digit starting with 7 is valid');
assert(validateNationalNumber('6123456789', 'IN') === '', 'India 10-digit starting with 6 is valid');
assert(validateNationalNumber('1234567890', 'IN').length > 0, 'India starting with 1 rejected');
assert(validateNationalNumber('919876543210', 'IN').length > 0, 'India 12 digits rejected');
assert(validateNationalNumber('987654', 'IN').length > 0, 'India fewer than 10 digits rejected');
assert(validateNationalNumber('98765abcde', 'IN').length > 0, 'Letters rejected');

// US validations
assert(validateNationalNumber('4155552671', 'US') === '', 'US valid 10-digit accepted');
assert(validateNationalNumber('12345', 'US').length > 0, 'US < 10 digits rejected');
assert(validateNationalNumber('415555267199', 'US').length > 0, 'US > 10 digits rejected');

// UK validations
assert(validateNationalNumber('7911123456', 'GB') === '', 'UK valid mobile accepted');
assert(validateNationalNumber('123', 'GB').length > 0, 'UK invalid number rejected');

// Canada validations
assert(validateNationalNumber('4165551234', 'CA') === '', 'Canada valid 10-digit accepted');
assert(validateNationalNumber('999', 'CA').length > 0, 'Canada invalid rejected');

console.log('\n--- 3. Testing Normalization to E.164 for Twilio ---');
assert(getNormalizedE164('9876543210', 'IN') === '+919876543210', 'India normalized to +919876543210');
assert(getNormalizedE164('4155552671', 'US') === '+14155552671', 'US normalized to +14155552671');
assert(getNormalizedE164('7911123456', 'GB') === '+447911123456', 'UK normalized to +447911123456');
assert(getNormalizedE164('4165551234', 'CA') === '+14165551234', 'Canada normalized to +14165551234');

console.log('\n--- 4. Testing Cascading Location Hierarchy ---');
assert(SUPPORTED_COUNTRIES.length === 4, 'Exactly 4 supported countries');
assert(SUPPORTED_COUNTRIES.includes('India'), 'India is supported');
assert(SUPPORTED_COUNTRIES.includes('United States'), 'United States is supported');
assert(SUPPORTED_COUNTRIES.includes('United Kingdom'), 'United Kingdom is supported');
assert(SUPPORTED_COUNTRIES.includes('Canada'), 'Canada is supported');

// Verify Maharashtra and Nanded
assert(LOCATION_DATA['India']['Maharashtra'] !== undefined, 'Maharashtra state exists in India');
assert(LOCATION_DATA['India']['Maharashtra'].includes('Nanded'), 'Nanded city exists in Maharashtra, India');

// Verify California and San Francisco
assert(LOCATION_DATA['United States']['California'] !== undefined, 'California exists in United States');
assert(LOCATION_DATA['United States']['California'].includes('San Francisco'), 'San Francisco exists in California');

// Verify UK and London
assert(LOCATION_DATA['United Kingdom']['England'] !== undefined, 'England exists in United Kingdom');
assert(LOCATION_DATA['United Kingdom']['England'].includes('London'), 'London exists in England');

// Verify Canada and Toronto
assert(LOCATION_DATA['Canada']['Ontario'] !== undefined, 'Ontario exists in Canada');
assert(LOCATION_DATA['Canada']['Ontario'].includes('Toronto'), 'Toronto exists in Ontario');

console.log(`\n========================================`);
console.log(`Results: ${passed} passed, ${failed} failed`);
console.log(`========================================`);
if (failed > 0) process.exit(1);

