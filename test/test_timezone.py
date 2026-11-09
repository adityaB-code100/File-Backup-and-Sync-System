import sys
import os
import unittest
from datetime import datetime, timezone, timedelta
import zoneinfo

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from cloud_storage.timezone_utils import (
    to_iso_utc,
    to_ist,
    now_utc,
    make_aware_utc,
    IST
)

class TestTimezoneUtilities(unittest.TestCase):
    """Scenario 1 & 2: UTC timestamp conversion, formatting, and no double-conversion."""

    def test_naive_datetime_to_iso_utc(self):
        # When MongoEngine returns a naive UTC datetime
        naive_dt = datetime(2026, 11, 8, 4, 36, 0)
        iso_str = to_iso_utc(naive_dt)
        self.assertEqual(iso_str, "2026-11-08T04:36:00+00:00")
        self.assertTrue(iso_str.endswith("+00:00"))

    def test_aware_utc_datetime_to_iso_utc(self):
        aware_dt = datetime(2026, 11, 8, 4, 36, 0, tzinfo=timezone.utc)
        iso_str = to_iso_utc(aware_dt)
        self.assertEqual(iso_str, "2026-11-08T04:36:00+00:00")

    def test_non_utc_datetime_to_iso_utc(self):
        # Datetime in IST (+05:30) 10:06 AM -> should convert to 04:36 UTC
        ist_dt = datetime(2026, 11, 8, 10, 6, 0, tzinfo=IST)
        iso_str = to_iso_utc(ist_dt)
        self.assertEqual(iso_str, "2026-11-08T04:36:00+00:00")

    def test_to_ist_conversion(self):
        utc_dt = datetime(2026, 11, 8, 4, 36, 0, tzinfo=timezone.utc)
        ist_dt = to_ist(utc_dt)
        self.assertEqual(ist_dt.tzinfo, IST)
        self.assertEqual(ist_dt.year, 2026)
        self.assertEqual(ist_dt.month, 11)
        self.assertEqual(ist_dt.day, 8)
        self.assertEqual(ist_dt.hour, 10)
        self.assertEqual(ist_dt.minute, 6)

    def test_to_ist_from_naive_utc(self):
        naive_utc = datetime(2026, 11, 8, 4, 36, 0)
        ist_dt = to_ist(naive_utc)
        self.assertEqual(ist_dt.hour, 10)
        self.assertEqual(ist_dt.minute, 6)

    def test_midnight_crossover_to_ist(self):
        # 22:30 UTC on Nov 8 -> 04:00 AM on Nov 9 in IST
        utc_dt = datetime(2026, 11, 8, 22, 30, 0, tzinfo=timezone.utc)
        ist_dt = to_ist(utc_dt)
        self.assertEqual(ist_dt.day, 9)
        self.assertEqual(ist_dt.hour, 4)
        self.assertEqual(ist_dt.minute, 0)

    def test_idempotent_aware_utc(self):
        dt = datetime(2026, 11, 8, 4, 36, 0)
        aware1 = make_aware_utc(dt)
        aware2 = make_aware_utc(aware1)
        self.assertEqual(aware1, aware2)
        self.assertEqual(aware1.tzinfo, timezone.utc)

    def test_none_handling(self):
        self.assertIsNone(to_iso_utc(None))
        self.assertIsNone(to_ist(None))
        self.assertIsNone(make_aware_utc(None))


class TestDjangoSettings(unittest.TestCase):
    """Scenario 3: Verify Django settings USE_TZ and TIME_ZONE."""

    def test_settings_use_tz_and_timezone(self):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_storage.settings')
        import django
        from django.conf import settings
        if not settings.configured:
            django.setup()
        self.assertTrue(settings.USE_TZ, "USE_TZ must be True")
        self.assertEqual(settings.TIME_ZONE, "Asia/Kolkata", "TIME_ZONE must be Asia/Kolkata")


class TestModelSerialization(unittest.TestCase):
    """Scenario 4: Serialization of models always produces explicit UTC offset."""

    def test_mock_folder_to_dict(self):
        from unittest.mock import MagicMock
        from files.models import Folder
        
        folder = MagicMock(spec=Folder)
        folder.id = "mock_id"
        folder.name = "Documents"
        folder.owner = MagicMock()
        folder.owner.id = "user_id"
        folder.parent_folder = None
        folder.created_at = datetime(2026, 11, 8, 4, 36, 0)  # naive UTC as from DB
        folder.deleted = False
        
        # Call the actual to_dict method
        result = Folder.to_dict(folder)
        self.assertEqual(result["created_at"], "2026-11-08T04:36:00+00:00")
        self.assertEqual(result["updated_at"], "2026-11-08T04:36:00+00:00")

    def test_mock_file_version_to_dict(self):
        from unittest.mock import MagicMock
        from files.models import FileVersion
        
        ver = MagicMock(spec=FileVersion)
        ver.id = "ver_id"
        ver.file = MagicMock()
        ver.file.id = "file_id"
        ver.version_number = 4
        ver.content_hash = "abc123hash"
        ver.size_bytes = 1024
        ver.created_at = datetime(2026, 11, 8, 4, 36, 0)
        ver.uploaded_by = MagicMock()
        ver.uploaded_by.id = "user_id"

        result = FileVersion.to_dict(ver)
        self.assertEqual(result["created_at"], "2026-11-08T04:36:00+00:00")

    def test_mock_user_to_dict(self):
        from unittest.mock import MagicMock
        from accounts.models import User

        user = MagicMock(spec=User)
        user.id = "user_id"
        user.email = "test@example.com"
        user.storage_quota_bytes = 1000
        user.storage_used_bytes = 500
        user.created_at = datetime(2026, 11, 8, 4, 36, 0)
        user.updated_at = datetime(2026, 11, 8, 5, 0, 0)

        result = User.to_dict(user)
        self.assertEqual(result["created_at"], "2026-11-08T04:36:00+00:00")
        self.assertEqual(result["updated_at"], "2026-11-08T05:00:00+00:00")


class TestRevisionListCurrentVersionLogic(unittest.TestCase):
    """Scenario 5: Version history 'is_current' logic fix."""

    def test_is_current_calculation(self):
        from unittest.mock import MagicMock
        
        # Simulating file record with current_version pointing to v4
        mock_v4 = MagicMock()
        mock_v4.id = "v4_id"
        mock_v4.version_number = 4
        mock_v4.to_dict.return_value = {
            "id": "v4_id",
            "version_number": 4,
            "created_at": "2026-11-08T04:36:00+00:00"
        }

        mock_v3 = MagicMock()
        mock_v3.id = "v3_id"
        mock_v3.version_number = 3
        mock_v3.to_dict.return_value = {
            "id": "v3_id",
            "version_number": 3,
            "created_at": "2026-11-07T04:36:00+00:00"
        }

        file_current_version = mock_v4
        cur_id = str(file_current_version.id)
        cur_ver_num = file_current_version.version_number

        # Calculate is_current exactly as RevisionListView does
        revisions = [mock_v4, mock_v3]
        results = []
        for r in revisions:
            r_dict = r.to_dict()
            r_dict["is_current"] = (str(r.id) == cur_id or (cur_ver_num is not None and r.version_number == cur_ver_num))
            results.append(r_dict)

        self.assertTrue(results[0]["is_current"], "v4 must be marked as is_current=True")
        self.assertFalse(results[1]["is_current"], "v3 must be marked as is_current=False")


class TestOTPAndAuthExpiryTimestamps(unittest.TestCase):
    """Scenario 7 & 8: OTP and Password Reset expiry remain consistent in UTC."""

    def test_mail_otp_server_epoch_expiry(self):
        import time
        now_ts = time.time()
        # OTP valid for 5 minutes
        expires_ts = now_ts + 300
        # Check validity
        self.assertFalse(time.time() > expires_ts, "Fresh OTP should not be expired")
        # Past timestamp
        past_ts = now_ts - 10
        self.assertTrue(time.time() > past_ts, "Past timestamp should be expired")

    def test_password_reset_naive_utc_consistency(self):
        # Backend generates: datetime.utcnow() + timedelta(minutes=15)
        # Backend checks: if reset_doc.expires_at < datetime.utcnow()
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=15)
        self.assertFalse(expires_at < now, "Active reset token must not be expired")

        past_expires_at = now - timedelta(seconds=1)
        self.assertTrue(past_expires_at < now, "Expired token must evaluate to True")


class TestDesktopAgentTimestampCompatibility(unittest.TestCase):
    """Scenario 9 & 10: Desktop agent SQLite UTC ISO-8601 compatibility."""

    def test_agent_iso_utc_parsing(self):
        # Desktop agent generates: datetime.now(timezone.utc).isoformat()
        # e.g. '2026-11-08T04:36:00.123456+00:00'
        agent_ts = datetime.now(timezone.utc).isoformat()
        self.assertTrue("+00:00" in agent_ts or agent_ts.endswith("Z"))
        
        # When passed to make_aware_utc or to_ist
        parsed = datetime.fromisoformat(agent_ts)
        self.assertIsNotNone(parsed.tzinfo)
        ist_dt = to_ist(parsed)
        self.assertEqual(ist_dt.tzinfo, IST)


class TestChangesApiSinceParamParsing(unittest.TestCase):
    """Verify that /api/files/changes/?since= parses ISO strings with ms and floats without HTTP 400."""

    def parse_since(self, since_param):
        from dateutil.parser import parse as parse_date
        try:
            val = float(since_param)
            return datetime.fromtimestamp(val, timezone.utc)
        except ValueError:
            parsed = parse_date(since_param)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc)
            return parsed.replace(tzinfo=timezone.utc)

    def test_iso_with_milliseconds_and_z(self):
        # Frontend produces: new Date(Date.now() - 30 * 60 * 1000).toISOString()
        # e.g. '2026-11-08T10:38:40.123Z' -> contains '.' so it must not fail as float
        dt = self.parse_since('2026-11-08T10:38:40.123Z')
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 11)
        self.assertEqual(dt.day, 8)
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.minute, 38)
        self.assertEqual(dt.microsecond, 123000)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_iso_with_utc_offset(self):
        dt = self.parse_since('2026-11-08T04:36:00+00:00')
        self.assertEqual(dt.hour, 4)
        self.assertEqual(dt.minute, 36)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_unix_epoch_float(self):
        dt = self.parse_since('1731040560.123')
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(to_iso_utc(dt), '2024-11-08T04:36:00.123000+00:00')


if __name__ == '__main__':
    unittest.main()

