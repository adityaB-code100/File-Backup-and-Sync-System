import {
  DISPLAY_TIMEZONE,
  parseDate,
  formatDateTime,
  formatDate,
  formatTime,
  formatRelativeTime
} from '../frontend/src/utils/dateUtils.js';

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

console.log('====================================================');
console.log(' VaultCloud Frontend Date & Timezone Unit Tests');
console.log(' Target Display Timezone: ' + DISPLAY_TIMEZONE);
console.log('====================================================\n');

// 1. Parsing Tests
console.log('--- 1. Testing parseDate ---');
const dUtcZ = parseDate('2026-11-08T04:36:00Z');
assert(dUtcZ !== null, 'Parses ISO string with trailing Z');
assert(dUtcZ.toISOString() === '2026-11-08T04:36:00.000Z', 'Maintains exact UTC moment from Z string');

const dUtcOffset = parseDate('2026-11-08T04:36:00+00:00');
assert(dUtcOffset !== null, 'Parses ISO string with explicit +00:00');
assert(dUtcOffset.toISOString() === '2026-11-08T04:36:00.000Z', 'Maintains exact UTC moment from +00:00 string');

const dNaive = parseDate('2026-11-08T04:36:00');
assert(dNaive !== null, 'Parses naive ISO string');
assert(dNaive.toISOString() === '2026-11-08T04:36:00.000Z', 'Naive ISO string is treated as UTC');

const dMillisNaive = parseDate('2026-11-08T10:06:25.119000');
assert(dMillisNaive !== null, 'Parses naive ISO string with fractional seconds');
assert(dMillisNaive.toISOString() === '2026-11-08T10:06:25.119Z', 'Fractional naive ISO string treated as UTC');

const dEpoch = parseDate(1731040560000);
assert(dEpoch !== null && !isNaN(dEpoch.getTime()), 'Parses epoch millisecond timestamp');

const dDateObj = parseDate(new Date('2026-11-08T04:36:00Z'));
assert(dDateObj !== null && dDateObj.getTime() === dUtcZ.getTime(), 'Preserves existing Date object');

assert(parseDate(null) === null, 'Returns null for null input');
assert(parseDate('') === null, 'Returns null for empty string');
assert(parseDate('not-a-date') === null, 'Returns null for invalid string');

// 2. IST Formatting Tests
console.log('\n--- 2. Testing IST Conversions (UTC+05:30) ---');
// 2026-11-08 04:36:00 UTC + 5:30 = 2026-11-08 10:06:00 IST
const formattedDT = formatDateTime('2026-11-08T04:36:00Z');
console.log('  formatDateTime output:', formattedDT);
assert(formattedDT.includes('8') && (formattedDT.includes('Nov') || formattedDT.includes('November')), 'Contains day 8 and Month Nov');
assert(formattedDT.includes('2026'), 'Contains year 2026');
assert(formattedDT.includes('10:06'), 'Converts 04:36 UTC to 10:06 IST');
assert(formattedDT.toLowerCase().includes('am'), 'Displays AM for 10:06');

const formattedDateOnly = formatDate('2026-11-08T04:36:00Z');
console.log('  formatDate output:', formattedDateOnly);
assert(formattedDateOnly.includes('8') && formattedDateOnly.includes('2026'), 'formatDate outputs correct date without time');

const formattedTimeOnly = formatTime('2026-11-08T04:36:00Z');
console.log('  formatTime output:', formattedTimeOnly);
assert(formattedTimeOnly.includes('10:06') && formattedTimeOnly.toLowerCase().includes('am'), 'formatTime outputs 10:06 am');

// 3. Midnight Crossover / Date Shift Test
console.log('\n--- 3. Testing Midnight Crossover & Date Shift ---');
// 2026-11-08 22:30:00 UTC + 05:30 = 2026-11-09 04:00:00 IST (crosses into next day!)
const midnightCross = formatDateTime('2026-11-08T22:30:00Z');
console.log('  Midnight crossover IST output:', midnightCross);
assert(midnightCross.includes('9') && midnightCross.includes('Nov'), 'Crosses over midnight to 9 Nov in IST');
assert(midnightCross.includes('04:00') || midnightCross.includes('4:00'), 'Displays 04:00 in IST');

// 4. Chronological Sorting Test across Midnight
console.log('\n--- 4. Testing Chronological Sorting with parseDate ---');
const items = [
  { id: 1, created_at: '2026-11-08T23:30:00Z' },
  { id: 2, created_at: '2026-11-08T04:36:00Z' },
  { id: 3, created_at: '2026-11-09T01:15:00+00:00' },
  { id: 4, created_at: '2026-11-08T18:00:00' } // naive
];
const sorted = [...items].sort((a, b) => parseDate(b.created_at).getTime() - parseDate(a.created_at).getTime());
assert(sorted[0].id === 3, 'Latest item is id 3 (Nov 9 01:15 UTC)');
assert(sorted[1].id === 1, 'Second latest is id 1 (Nov 8 23:30 UTC)');
assert(sorted[2].id === 4, 'Third latest is id 4 (Nov 8 18:00 naive UTC)');
assert(sorted[3].id === 2, 'Earliest item is id 2 (Nov 8 04:36 UTC)');

// 5. No Double-Conversion Verification
console.log('\n--- 5. Testing Idempotency & No Double Conversion ---');
const firstPass = parseDate('2026-11-08T04:36:00Z');
const secondPass = parseDate(firstPass);
assert(firstPass.getTime() === secondPass.getTime(), 'Parsing an existing parsed date preserves UTC epoch ms');
const dt1 = formatDateTime(firstPass);
const dt2 = formatDateTime(secondPass);
assert(dt1 === dt2, 'Formatting the date repeatedly yields identical IST string');

// 6. Relative Time Formatting
console.log('\n--- 6. Testing formatRelativeTime ---');
const now = Date.now();
assert(formatRelativeTime(new Date(now - 10000)) === 'Just now', 'Less than 60 seconds returns "Just now"');
assert(formatRelativeTime(new Date(now - 180000)) === '3m ago', '3 minutes ago returns "3m ago"');
assert(formatRelativeTime(new Date(now + 5000)) === 'Just now', 'Slight clock skew into future returns "Just now"');

console.log(`\n====================================================`);
console.log(` Results: ${passed} passed, ${failed} failed`);
console.log(`====================================================\n`);

if (failed > 0) {
  process.exit(1);
} else {
  console.log('ALL FRONTEND TIMEZONE & DATE UTILS TESTS PASSED!');
}

