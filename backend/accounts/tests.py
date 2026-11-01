import os
import urllib.parse
from pathlib import Path
import pytest
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
        me.disconnect()
        me.connect(host=TEST_MONGO_URI)
        User.objects.delete()
        PasswordResetToken.objects.delete()
        self.client = APIClient()

    def tearDown(self):
        User.objects.delete()
        PasswordResetToken.objects.delete()
        me.disconnect()

    def test_register_login_refresh_flow(self):
        # 1. Register User
        reg_resp = self.client.post('/api/auth/register/', {
            'email': 'testuser@example.com',
            'password': 'StrongPassword123!'
        }, format='json')
        self.assertEqual(reg_resp.status_code, 201)
        self.assertIn('access', reg_resp.data)
        self.assertIn('refresh', reg_resp.data)
        self.assertEqual(reg_resp.data['user']['email'], 'testuser@example.com')

        # 2. Login User
        login_resp = self.client.post('/api/auth/login/', {
            'email': 'testuser@example.com',
            'password': 'StrongPassword123!'
        }, format='json')
        self.assertEqual(login_resp.status_code, 200)
        access_token = login_resp.data['access']
        refresh_token = login_resp.data['refresh']

        # 3. Access Protected Route (/api/auth/me/)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_resp = self.client.get('/api/auth/me/')
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.data['email'], 'testuser@example.com')

        # 4. Refresh Token Flow
        ref_resp = self.client.post('/api/auth/refresh/', {
            'refresh': refresh_token
        }, format='json')
        self.assertEqual(ref_resp.status_code, 200)
        self.assertIn('access', ref_resp.data)

    def test_password_reset_end_to_end(self):
        """Test full password reset lifecycle: request -> token generation -> validation -> single-use -> new password login."""
        # 1. Create target user
        user = User(email='resetuser@example.com')
        user.set_password('OldPassword123!')
        user.save()

        # 2. Request password reset
        req_resp = self.client.post('/api/auth/password-reset/', {'email': 'resetuser@example.com'}, format='json')
        self.assertEqual(req_resp.status_code, 200)
        self.assertIn('detail', req_resp.data)

        # Retrieve the generated token from database
        token_doc = PasswordResetToken.objects(user=user, used=False).first()
        self.assertIsNotNone(token_doc, "PasswordResetToken document was not created.")
        self.assertFalse(token_doc.used)

        # Use dev_token returned in DEBUG mode
        dev_token = req_resp.data.get('dev_token')
        self.assertIsNotNone(dev_token, "dev_token missing in test response.")

        # 3. Reject invalid token
        invalid_resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': 'invalid-token-12345',
            'new_password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(invalid_resp.status_code, 400)

        # 4. Confirm password reset with valid token
        confirm_resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': dev_token,
            'new_password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertIn('detail', confirm_resp.data)

        # 5. Token is now single-use -> replay attempt must fail
        replay_resp = self.client.post('/api/auth/password-reset/confirm/', {
            'token': dev_token,
            'new_password': 'AnotherPassword123!'
        }, format='json')
        self.assertEqual(replay_resp.status_code, 400)

        # 6. Verify old password no longer works
        old_login = self.client.post('/api/auth/login/', {
            'email': 'resetuser@example.com',
            'password': 'OldPassword123!'
        }, format='json')
        self.assertEqual(old_login.status_code, 401)

        # 7. Verify new password succeeds
        new_login = self.client.post('/api/auth/login/', {
            'email': 'resetuser@example.com',
            'password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(new_login.status_code, 200)
        self.assertIn('access', new_login.data)
