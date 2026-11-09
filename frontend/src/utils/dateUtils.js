/**
 * VaultCloud Unified Date & Time Formatting Utilities
 *
 * Target Display Timezone: India Standard Time (IST)
 * - IANA: Asia/Kolkata
 * - Offset: UTC+05:30
 *
 * Backend & Database storage: UTC (ISO-8601)
 */
export const DISPLAY_TIMEZONE = 'Asia/Kolkata';

/**
 * Safely parses any date input (ISO string with or without Z, epoch ms, or Date object)
 * into a valid Date object.
 * If an ISO string has no timezone indicator, appends 'Z' to treat it as UTC.
 */
export function parseDate(value) {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (typeof value === 'string') {
    let str = value.trim();
    if (!str) return null;

    // If ISO-8601 format without timezone offset or trailing Z, treat as UTC
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(str)) {
      str += 'Z';
    }

    const d = new Date(str);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  if (typeof value === 'number') {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  return null;
}

/**
 * Formats a date/time into IST string: e.g. "8 Nov 2026, 10:06 am"
 */
export function formatDateTime(value, options = {}) {
  const d = parseDate(value);
  if (!d) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: DISPLAY_TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    ...options,
  }).format(d);
}

/**
 * Formats a date into IST string without time: e.g. "8 Nov 2026"
 */
export function formatDate(value, options = {}) {
  const d = parseDate(value);
  if (!d) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: DISPLAY_TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    ...options,
  }).format(d);
}

/**
 * Formats time only in IST: e.g. "10:06 am"
 */
export function formatTime(value, options = {}) {
  const d = parseDate(value);
  if (!d) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: DISPLAY_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    ...options,
  }).format(d);
}

/**
 * Formats relative time for recent events (e.g. "Just now", "5m ago"),
 * falling back to formatTime or formatDateTime for older items.
 */
export function formatRelativeTime(value) {
  const d = parseDate(value);
  if (!d) return '—';

  const now = new Date();
  const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);

  if (diffSec < 0) {
    // Clock skew / slightly in future
    return 'Just now';
  }
  if (diffSec < 60) {
    return 'Just now';
  }
  if (diffSec < 3600) {
    return `${Math.floor(diffSec / 60)}m ago`;
  }
  if (diffSec < 86400) {
    return formatTime(d);
  }

  return formatDateTime(d);
}

