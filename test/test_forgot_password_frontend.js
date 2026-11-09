/**
 * Unit and security tests for ForgotPasswordPage and App routing
 */
import fs from 'fs';
import path from 'path';

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
console.log(' VaultCloud Forgot Password Frontend Security Tests');
console.log('====================================================\n');

// 1. Static & Security Audit of ForgotPasswordPage.jsx
console.log('--- 1. Static Audit of ForgotPasswordPage.jsx ---');
const forgotPageSource = fs.readFileSync('frontend/src/components/ForgotPasswordPage.jsx', 'utf-8');

assert(
  forgotPageSource.includes("const [verificationCode, setVerificationCode] = useState('');") ||
  forgotPageSource.includes('const [verificationCode, setVerificationCode] = useState("");'),
  'Verification code state starts strictly as empty string'
);

assert(
  !forgotPageSource.includes('setVerificationCode(res.data') &&
  !forgotPageSource.includes('setToken(res.data'),
  'Verification code is NEVER copied from an API response into React state'
);

assert(
  !forgotPageSource.includes('localStorage.getItem') &&
  !forgotPageSource.includes('sessionStorage.getItem'),
  'Verification code is NOT populated from localStorage or sessionStorage'
);

assert(
  !forgotPageSource.includes('URLSearchParams') &&
  !forgotPageSource.includes('location.search'),
  'Verification code is NOT populated from URL query parameters'
);

assert(
  forgotPageSource.includes('autoComplete="off"'),
  'Input uses autoComplete="off" to prevent unintentional browser autofill'
);

assert(
  forgotPageSource.includes('maxLength={6}'),
  'Input enforces maxLength={6}'
);

assert(
  forgotPageSource.includes('inputMode="numeric"'),
  'Input specifies inputMode="numeric"'
);

assert(
  forgotPageSource.includes(".replace(/\\D/g, '').slice(0, 6)") ||
  forgotPageSource.includes('.replace(/\\D/g, "").slice(0, 6)'),
  'Input sanitizes value to digits only and strictly max 6 digits'
);

// 2. Input Sanitization Simulation
console.log('\n--- 2. Input Sanitization Logic Tests ---');
const sanitize = (val) => String(val || '').replace(/\D/g, '').slice(0, 6);

assert(sanitize('464929') === '464929', 'Preserves clean 6-digit numeric code');
assert(sanitize('46-49-29') === '464929', 'Strips dashes');
assert(sanitize('abc464929xyz') === '464929', 'Strips letters');
assert(sanitize('123456789') === '123456', 'Truncates to exactly 6 digits');
assert(sanitize('') === '', 'Empty string remains empty');
assert(sanitize(null) === '', 'Null input returns empty');

// 3. Validation Logic Simulation
console.log('\n--- 3. Client-Side Validation Logic Tests ---');
const validateReset = (code, newPw, confirmPw, email) => {
  if (!code || !code.trim()) return 'Please enter the 6-digit verification code from your email.';
  if (code.trim().length !== 6) return 'Verification code must be exactly 6 digits.';
  if (!newPw) return 'Please enter your new password.';
  if (newPw.length < 8) return 'New password must be at least 8 characters.';
  if (newPw !== confirmPw) return 'Passwords do not match.';
  
  const emailLower = (email || '').trim().toLowerCase();
  const emailLocal = emailLower.split('@')[0];
  if (newPw.toLowerCase() === emailLower || (emailLocal && newPw.toLowerCase() === emailLocal)) {
    return 'Password cannot be the same as your email address.';
  }
  return null;
};

assert(
  validateReset('', 'Password123!', 'Password123!', 'user@example.com') === 'Please enter the 6-digit verification code from your email.',
  'Rejects empty verification code'
);

assert(
  validateReset('12345', 'Password123!', 'Password123!', 'user@example.com') === 'Verification code must be exactly 6 digits.',
  'Rejects verification code shorter than 6 digits'
);

assert(
  validateReset('123456', 'short', 'short', 'user@example.com') === 'New password must be at least 8 characters.',
  'Rejects password shorter than 8 characters'
);

assert(
  validateReset('123456', 'Password123!', 'DifferentPassword123!', 'user@example.com') === 'Passwords do not match.',
  'Rejects mismatched passwords'
);

assert(
  validateReset('123456', 'user@example.com', 'user@example.com', 'user@example.com') === 'Password cannot be the same as your email address.',
  'Rejects password matching email'
);

assert(
  validateReset('123456', 'myusername', 'myusername', 'myusername@example.com') === 'Password cannot be the same as your email address.',
  'Rejects password matching email local-part'
);

assert(
  validateReset('123456', 'SuperSecurePass2026!', 'SuperSecurePass2026!', 'user@example.com') === null,
  'Accepts valid verification code and valid new password'
);

// 4. App.jsx Route Resolution Audit
console.log('\n--- 4. App.jsx Route Resolution Audit ---');
const appSource = fs.readFileSync('frontend/src/App.jsx', 'utf-8');

assert(
  appSource.includes("path === '/forgot-password'"),
  'App.jsx maps /forgot-password pathname directly'
);

assert(
  appSource.includes('popstate'),
  'App.jsx synchronizes browser history via popstate event'
);

assert(
  appSource.includes('history.pushState'),
  'App.jsx updates browser URL via history.pushState'
);

assert(
  appSource.includes('const [page, setPage] = useState(getPageFromPath)'),
  'App.jsx initializes router state from current window.location.pathname'
);

console.log(`\n====================================================`);
console.log(` Results: ${passed} passed, ${failed} failed`);
console.log(`====================================================\n`);

if (failed > 0) {
  process.exit(1);
} else {
  console.log('ALL FRONTEND SECURITY AND VALIDATION TESTS PASSED!');
}
