import { parsePhoneNumberFromString } from 'libphonenumber-js';
import { DIAL_COUNTRIES, DIAL_CODES } from '../data/locations.js';

/**
 * Parses a stored mobile number string into countryCode ('IN', 'US', 'GB', 'CA')
 * and nationalNumber.
 * 
 * Supports:
 * - Full E.164 format (+919876543210, +14155552671, +447911123456, +14165551234)
 * - Raw digits without leading +
 * - Unparseable raw strings (preserves user value for correction)
 */
export const parseStoredMobile = (rawMobile) => {
  if (!rawMobile || typeof rawMobile !== 'string') {
    return { countryCode: 'IN', dialCode: '+91', nationalNumber: '' };
  }

  const trimmed = rawMobile.trim();
  if (!trimmed) {
    return { countryCode: 'IN', dialCode: '+91', nationalNumber: '' };
  }

  // Attempt standard parsing via libphonenumber-js
  try {
    const parsed = parsePhoneNumberFromString(trimmed);
    if (parsed) {
      const country = parsed.country; // e.g. 'IN', 'US', 'GB', 'CA'
      const callingCode = `+${parsed.countryCallingCode}`;
      const national = parsed.nationalNumber || '';

      if (country && ['IN', 'US', 'GB', 'CA'].includes(country)) {
        return {
          countryCode: country,
          dialCode: DIAL_CODES[country] || callingCode,
          nationalNumber: national,
        };
      }

      // If country is not strictly in our 4, but dialCode matches:
      if (callingCode === '+91') {
        return { countryCode: 'IN', dialCode: '+91', nationalNumber: national };
      }
      if (callingCode === '+44') {
        return { countryCode: 'GB', dialCode: '+44', nationalNumber: national };
      }
      if (callingCode === '+1') {
        // Can be US or CA
        return { countryCode: country === 'CA' ? 'CA' : 'US', dialCode: '+1', nationalNumber: national };
      }
    }
  } catch (err) {
    // ignore parse errors and proceed to fallback
  }

  // Fallback prefix matching
  if (trimmed.startsWith('+91')) {
    return { countryCode: 'IN', dialCode: '+91', nationalNumber: trimmed.slice(3).replace(/[^\d]/g, '') };
  }
  if (trimmed.startsWith('+44')) {
    return { countryCode: 'GB', dialCode: '+44', nationalNumber: trimmed.slice(3).replace(/[^\d]/g, '') };
  }
  if (trimmed.startsWith('+1')) {
    return { countryCode: 'US', dialCode: '+1', nationalNumber: trimmed.slice(2).replace(/[^\d]/g, '') };
  }

  // If number has no +, attempt parse assuming default 'IN'
  try {
    const parsedIn = parsePhoneNumberFromString(trimmed, 'IN');
    if (parsedIn && parsedIn.isValid()) {
      return { countryCode: 'IN', dialCode: '+91', nationalNumber: parsedIn.nationalNumber };
    }
  } catch (e) {
    // ignore
  }

  // If completely unrecognized, display raw value for correction
  return {
    countryCode: 'IN',
    dialCode: '+91',
    nationalNumber: trimmed.replace(/^\+/, ''),
  };
};

/**
 * Validates a national mobile number for the selected country.
 * Returns empty string '' if valid or optional, or a specific error message.
 */
export const validateNationalNumber = (national, countryCode = 'IN') => {
  if (!national || !national.trim()) {
    return ''; // Mobile number is optional if user hasn't added one
  }

  const cleaned = national.trim().replace(/[\s\-()]/g, '');

  if (/[^\d]/.test(cleaned)) {
    return 'Mobile number must contain digits only. Do not include country codes or letters.';
  }

  if (countryCode === 'IN') {
    if (cleaned.length !== 10) {
      return 'Indian mobile numbers must be exactly 10 digits.';
    }
    if (!/^[6-9]\d{9}$/.test(cleaned)) {
      return 'Indian mobile numbers must start with 6, 7, 8, or 9.';
    }
    const parsed = parsePhoneNumberFromString(cleaned, 'IN');
    if (!parsed || !parsed.isValid()) {
      return 'Please enter a valid 10-digit Indian mobile number.';
    }
    return '';
  }

  if (countryCode === 'US') {
    if (cleaned.length !== 10) {
      return 'US mobile numbers must be a valid 10-digit national number.';
    }
    const parsed = parsePhoneNumberFromString(cleaned, 'US');
    if (!parsed || !parsed.isValid()) {
      return 'Please enter a valid 10-digit US mobile number.';
    }
    return '';
  }

  if (countryCode === 'CA') {
    if (cleaned.length !== 10) {
      return 'Canadian mobile numbers must be a valid 10-digit national number.';
    }
    const parsed = parsePhoneNumberFromString(cleaned, 'CA');
    if (!parsed || !parsed.isValid()) {
      return 'Please enter a valid 10-digit Canadian mobile number.';
    }
    return '';
  }

  if (countryCode === 'GB') {
    const parsed = parsePhoneNumberFromString(cleaned, 'GB');
    if (!parsed || !parsed.isValid()) {
      return 'Please enter a valid UK mobile number.';
    }
    return '';
  }

  return '';
};

/**
 * Formats countryCode + nationalNumber into normalized E.164 string (+[countryCode][national])
 */
export const getNormalizedE164 = (national, countryCode = 'IN') => {
  if (!national || !national.trim()) return '';
  const cleaned = national.trim().replace(/[\s\-()]/g, '');
  if (!cleaned) return '';

  try {
    const parsed = parsePhoneNumberFromString(cleaned, countryCode);
    if (parsed && parsed.isValid()) {
      return parsed.format('E.164');
    }
  } catch (e) {
    // fallback
  }

  const dial = DIAL_CODES[countryCode] || '+91';
  return `${dial}${cleaned}`;
};

/**
 * Returns formatted display string for View Mode, e.g. "🇮🇳 +91 9876543210"
 */
export const formatDisplayMobile = (rawMobile) => {
  if (!rawMobile) return null;
  const { countryCode, dialCode, nationalNumber } = parseStoredMobile(rawMobile);
  const countryObj = DIAL_COUNTRIES.find((c) => c.code === countryCode);
  const flag = countryObj?.flag || '';
  if (!nationalNumber) return rawMobile;
  return `${flag} ${dialCode} ${nationalNumber}`.trim();
};
