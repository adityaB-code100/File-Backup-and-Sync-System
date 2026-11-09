from datetime import datetime, timezone
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

def now_utc():
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)

def make_aware_utc(dt):
    """Ensures a datetime object is timezone-aware in UTC."""
    if not dt:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def to_iso_utc(dt):
    """
    Serializes a datetime object into a standard ISO-8601 string with explicit UTC offset (+00:00).
    Prevents browsers and API consumers from mistakenly interpreting naive UTC datetimes as local time.
    """
    if not dt:
        return None
    if not isinstance(dt, datetime):
        return str(dt)
    aware = make_aware_utc(dt)
    return aware.isoformat()

def to_ist(dt):
    """Converts any datetime to IST (Asia/Kolkata)."""
    if not dt:
        return None
    aware = make_aware_utc(dt)
    return aware.astimezone(IST)

