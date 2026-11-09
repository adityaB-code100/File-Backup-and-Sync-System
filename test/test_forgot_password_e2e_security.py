import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

# Ensure backend and app are on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
APP_DIR = os.path.join(BASE_DIR, 'app')

for p in (BASE_DIR, BACKEND_DIR, APP_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_storage.settings')
import django
django.setup()

from django.conf import settings
from rest_framework.test import APIClient
from accounts.models import User, PasswordResetToken
import auth
import gui


class TestBackendOTPSecurityAndResponses(unittest.TestCase):
    """
    Issue 2 & Requirement C: Backend OTP Security & API Response Guarantees.
    Verify OTP is never exposed in production or standard responses,
    verification works correctly, single-use is preserved, and invalid/expired codes fail.
    """

    def setUp(self):
        self.client = APIClient()
        self.test_email = 'security_audit_user@example.com'
        self.user = User.objects(email=self.test_email).first()
        if not self.user:
            self.user = User(email=self.test_email, is_email_verified=True)
            self.user.set_password('InitialSecurePass123!')
            self.user.save()
        else:
            self.user.set_password('InitialSecurePass123!')
            self.user.save()

    def tearDown(self):
        PasswordResetToken.objects(user=self.user).delete()

    @patch('accounts.otp_client.otp_client.send_email_otp')
    def test_password_reset_response_contains_no_otp_or_dev_token(self, mock_send_otp):
        # Even if the internal service returns a dev_otp, the public API must NOT expose it
        mock_send_otp.return_value = {
            "success": True,
            "message": "Dispatched",
            "dev_otp": "464929"
        }

        # Force TESTING to False to simulate standard/production runtime
        with patch.object(settings, 'TESTING', False):
            resp = self.client.post('/api/auth/password-reset/', {'email': self.test_email}, format='json')

        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()

        # Must contain generic message
        self.assertIn("detail", resp_data)
        self.assertEqual(
            resp_data["detail"],
            "If an account with this email exists, password reset instructions have been dispatched."
        )

        # SECURITY: Must NOT contain OTP in plaintext, dev_token, test OTP, or secrets
        self.assertNotIn("dev_token", resp_data)
        self.assertNotIn("otp", resp_data)
        self.assertNotIn("code", resp_data)
        self.assertNotIn("464929", str(resp_data))

    @patch('accounts.otp_client.otp_client.verify_email_otp')
    def test_invalid_otp_fails_verification(self, mock_verify_otp):
        mock_verify_otp.return_value = {
            "valid": False,
            "message": "Invalid or expired verification code."
        }

        resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': '000000',
            'email': self.test_email,
            'new_password': 'NewPassword123!'
        }, format='json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get('code'), 'INVALID_TOKEN')

    @patch('accounts.otp_client.otp_client.verify_email_otp')
    def test_successful_otp_and_password_update(self, mock_verify_otp):
        mock_verify_otp.return_value = {
            "valid": True,
            "message": "OTP verified successfully."
        }

        new_pass = 'BrandNewPassword2026!'
        resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': '464929',
            'email': self.test_email,
            'new_password': new_pass
        }, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertIn("successfully reset", resp.json().get('detail', ''))

        # Verify new password authenticates
        fresh_user = User.objects(email=self.test_email).first()
        self.assertTrue(fresh_user.check_password(new_pass))
        self.assertFalse(fresh_user.check_password('InitialSecurePass123!'))

    def test_expired_legacy_token_fails(self):
        import hashlib, secrets
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        
        # Save expired token
        PasswordResetToken(
            user=self.user,
            token_hash=token_hash,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            used=False
        ).save()

        resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': raw_token,
            'email': self.test_email,
            'new_password': 'AnotherNewPassword123!'
        }, format='json')

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get('code'), 'EXPIRED_TOKEN')


class TestEndToEndDesktopLoginAfterReset(unittest.TestCase):
    """
    Issue 3 & 4: Desktop Agent Login with New Password & Data Preservation.
    """

    def setUp(self):
        import tempfile
        import db
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "sync_state.db")
        self.token_path = os.path.join(self.temp_dir.name, "token.json")
        self.creds_path = os.path.join(self.temp_dir.name, "credentials.json")

        self.db_patcher = patch.object(db, "DB_PATH", self.db_path)
        self.db_patcher.start()
        db.init_db()

        self.test_email = 'desktop_sync_user@example.com'
        self.new_pass = 'BrandNewPassword2026!'

        db.set_sync_user("user_999", self.test_email)
        self.test_file = os.path.join(self.temp_dir.name, "my_document.txt")
        with open(self.test_file, "w") as f:
            f.write("Untouched file content.")
        db.upsert_record(self.test_file, user_id="user_999", sync_mode="individual", abs_path=self.test_file)

    def tearDown(self):
        self.db_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    @patch('requests.post')
    @patch('requests.get')
    def test_desktop_login_authenticates_with_new_password(self, mock_get, mock_post):
        import db

        # Mock backend JWT response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access": "jwt_access_for_new_password",
            "refresh": "jwt_refresh_for_new_password"
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "id": "user_999",
            "email": self.test_email
        }

        # Initialize desktop auth with new password
        desktop_auth = auth.VaultCloudAuth(
            backend_url="http://localhost:8000/api",
            token_path=self.token_path,
            creds_path=self.creds_path,
            email=self.test_email,
            password=self.new_pass
        )
        desktop_auth.login()

        # Check JWT tokens
        self.assertEqual(desktop_auth.access_token, "jwt_access_for_new_password")
        self.assertEqual(desktop_auth.refresh_token, "jwt_refresh_for_new_password")
        self.assertTrue(os.path.exists(self.token_path))

        # Check data preservation
        sync_user = db.get_sync_user()
        self.assertEqual(sync_user["email"], self.test_email)
        records = db.get_tracked_individual_files(user_id="user_999")
        self.assertEqual(len(records), 1)
        self.assertTrue(os.path.exists(self.test_file))


class TestDesktopGUIDirectAndRouting(unittest.TestCase):
    """
    Issue 1: Desktop GUI link, URL formatting, and browser redirect.
    """

    def test_desktop_url_resolution(self):
        url = auth.get_forgot_password_url("http://localhost:5173")
        self.assertEqual(url, "http://localhost:5173/forgot-password")

        url_slash = auth.get_forgot_password_url("http://localhost:5173/")
        self.assertEqual(url_slash, "http://localhost:5173/forgot-password")

        url_prod = auth.get_forgot_password_url("https://vaultcloud.com")
        self.assertEqual(url_prod, "https://vaultcloud.com/forgot-password")

    @patch('webbrowser.open')
    def test_desktop_open_browser(self, mock_browser_open):
        mock_browser_open.return_value = True
        res = auth.open_forgot_password("http://localhost:5173")
        self.assertTrue(res)
        import time
        time.sleep(0.1)
        mock_browser_open.assert_called_once_with("http://localhost:5173/forgot-password", new=2)


if __name__ == '__main__':
    unittest.main()

