import os
import urllib.parse
from pathlib import Path
from unittest.mock import patch
import mongoengine as me
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from accounts.models import User, PasswordResetToken
from dotenv import load_dotenv

load_dotenv(Path(settings.BASE_DIR) / '../.env')
ENV_MONGO_URI = os.environ.get('MONGO_URI')
if not ENV_MONGO_URI:
    ENV_MONGO_URI = getattr(settings, 'MONGO_URI', 'mongodb://localhost:27017/cloud_storage_test_db')

parsed = urllib.parse.urlparse(ENV_MONGO_URI)
if 'mongodb+srv' in ENV_MONGO_URI:
    path_parts = parsed.path.split('/')
    if len(path_parts) > 1:
        path_parts[1] = 'cloud_storage_test_db'
    parsed = parsed._replace(path="/".join(path_parts))
    TEST_MONGO_URI = urllib.parse.urlunparse(parsed)
else:
    TEST_MONGO_URI = 'mongodb://localhost:27017/cloud_storage_test_db'

@override_settings(MONGO_URI=TEST_MONGO_URI)
class AccountsAuthTestCase(TestCase):
    def setUp(self):
        try:
            me.disconnect()
            me.connect(host=TEST_MONGO_URI)
            User.objects.delete()
            PasswordResetToken.objects.delete()
        except Exception:
            pass
        self.client = APIClient()

    def tearDown(self):
        try:
            User.objects.delete()
            PasswordResetToken.objects.delete()
            me.disconnect()
        except Exception:
            pass

    @patch('accounts.otp_client.otp_client.send_email_otp')
    @patch('accounts.otp_client.otp_client.verify_email_otp')
    def test_registration_with_email_otp_flow(self, mock_verify, mock_send):
        mock_send.return_value = {"success": True, "message": "Dispatched", "dev_otp": "654321"}
        mock_verify.return_value = {"valid": True, "message": "Email verified successfully."}

        # 1. Register User (unverified)
        reg_resp = self.client.post('/api/auth/register/', {
            'email': 'newuser@example.com',
            'password': 'StrongPassword123!',
            'full_name': 'Jane Doe'
        }, format='json')
        self.assertEqual(reg_resp.status_code, 201)
        self.assertTrue(reg_resp.data.get('requires_verification'))
        self.assertFalse(reg_resp.data.get('is_email_verified'))

        # 2. Login fails before OTP verification (403 Forbidden)
        unverified_login = self.client.post('/api/auth/login/', {
            'email': 'newuser@example.com',
            'password': 'StrongPassword123!'
        }, format='json')
        self.assertEqual(unverified_login.status_code, 403)
        self.assertEqual(unverified_login.data.get('code'), 'EMAIL_NOT_VERIFIED')

        # 3. Verify Email OTP
        verify_resp = self.client.post('/api/auth/verify-email-otp/', {
            'email': 'newuser@example.com',
            'otp': '654321'
        }, format='json')
        self.assertEqual(verify_resp.status_code, 200)
        self.assertIn('access', verify_resp.data)
        self.assertIn('refresh', verify_resp.data)
        self.assertTrue(verify_resp.data['user']['is_email_verified'])

        # 4. Login now succeeds
        login_resp = self.client.post('/api/auth/login/', {
            'email': 'newuser@example.com',
            'password': 'StrongPassword123!'
        }, format='json')
        self.assertEqual(login_resp.status_code, 200)
        access_token = login_resp.data['access']
        refresh_token = login_resp.data['refresh']

        # 5. Access Protected Route (/api/auth/me/)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_resp = self.client.get('/api/auth/me/')
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.data['email'], 'newuser@example.com')

        # 6. Refresh Token Flow
        ref_resp = self.client.post('/api/auth/refresh/', {
            'refresh': refresh_token
        }, format='json')
        self.assertEqual(ref_resp.status_code, 200)
        self.assertIn('access', ref_resp.data)

    def test_profile_update_and_mobile_verification(self):
        # Create active verified user
        user = User(email='profileuser@example.com', is_email_verified=True)
        user.set_password('Password123!')
        user.save()

        # Login
        login_resp = self.client.post('/api/auth/login/', {
            'email': 'profileuser@example.com',
            'password': 'Password123!'
        }, format='json')
        self.assertEqual(login_resp.status_code, 200)
        access = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        # 1. Update Profile Fields
        update_resp = self.client.put('/api/auth/profile/', {
            'full_name': 'Profile Tester',
            'mobile_number': '+14155552671',
            'city': 'San Francisco',
            'state': 'California',
            'country': 'United States',
            'address': '123 Market St'
        }, format='json')
        self.assertEqual(update_resp.status_code, 200)
        user_data = update_resp.data['user']
        self.assertEqual(user_data['full_name'], 'Profile Tester')
        self.assertEqual(user_data['mobile_number'], '+14155552671')
        self.assertFalse(user_data['is_mobile_verified'])

        # 2. Send Mobile OTP (with mocked client)
        with patch('accounts.otp_client.otp_client.send_sms_otp') as mock_sms_send:
            mock_sms_send.return_value = {"success": True, "message": "Dispatched", "dev_otp": "777888"}
            sms_send_resp = self.client.post('/api/auth/mobile/send-otp/', {
                'phone': '+14155552671'
            }, format='json')
            self.assertEqual(sms_send_resp.status_code, 200)

        # 3. Verify Mobile OTP (with mocked client)
        with patch('accounts.otp_client.otp_client.verify_sms_otp') as mock_sms_verify:
            mock_sms_verify.return_value = {"valid": True, "message": "Phone verified"}
            sms_verify_resp = self.client.post('/api/auth/mobile/verify-otp/', {
                'otp': '777888'
            }, format='json')
            self.assertEqual(sms_verify_resp.status_code, 200)
            self.assertTrue(sms_verify_resp.data['user']['is_mobile_verified'])

        # 4. Change Password
        cp_resp = self.client.post('/api/auth/change-password/', {
            'current_password': 'Password123!',
            'new_password': 'BrandNewPassword123!'
        }, format='json')
        self.assertEqual(cp_resp.status_code, 200)

        # 5. Verify old password fails, new succeeds
        old_login = self.client.post('/api/auth/login/', {
            'email': 'profileuser@example.com',
            'password': 'Password123!'
        }, format='json')
        self.assertEqual(old_login.status_code, 401)

        new_login = self.client.post('/api/auth/login/', {
            'email': 'profileuser@example.com',
            'password': 'BrandNewPassword123!'
        }, format='json')
        self.assertEqual(new_login.status_code, 200)

    @patch('accounts.otp_client.otp_client.verify_email_otp')
    @patch('accounts.otp_client.otp_client.send_email_otp')
    def test_password_reset_end_to_end(self, mock_otp_send, mock_otp_verify):
        mock_otp_send.return_value = {"success": True, "message": "Dispatched", "dev_otp": "123456"}
        mock_otp_verify.return_value = {"valid": True, "message": "Verified"}

        user = User(email='resetuser@example.com', is_email_verified=True)
        user.set_password('OldPassword123!')
        user.save()

        # Request reset
        req_resp = self.client.post('/api/auth/password-reset/', {'email': 'resetuser@example.com'}, format='json')
        self.assertEqual(req_resp.status_code, 200)

        dev_token = req_resp.data.get('dev_token')
        self.assertIsNotNone(dev_token)

        # Confirm with valid token
        confirm_resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': dev_token,
            'email': 'resetuser@example.com',
            'new_password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 200)

        # Login with new password
        new_login = self.client.post('/api/auth/login/', {
            'email': 'resetuser@example.com',
            'password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(new_login.status_code, 200)
