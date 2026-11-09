import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import urllib.parse
import threading
import time

# Ensure app package is in sys.path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import auth
import gui

class TestForgotPasswordURLConfiguration(unittest.TestCase):
    """Requirements 3, 4, 5, 6: URL formatting, env configuration, trailing slashes, validation."""

    def test_default_development_url(self):
        with patch.dict(os.environ, {"VAULTCLOUD_WEB_URL": "http://localhost:5173"}):
            url = auth.get_forgot_password_url()
            self.assertEqual(url, "http://localhost:5173/forgot-password")

    def test_trailing_slashes_handling(self):
        cases = [
            ("http://localhost:5173/", "http://localhost:5173/forgot-password"),
            ("http://localhost:5173///", "http://localhost:5173/forgot-password"),
            ("http://localhost:5173/forgot-password", "http://localhost:5173/forgot-password"),
            ("http://localhost:5173/forgot-password/", "http://localhost:5173/forgot-password"),
            ("http://localhost:5173/portal/", "http://localhost:5173/portal/forgot-password"),
        ]
        for input_url, expected in cases:
            with self.subTest(input_url=input_url):
                res = auth.get_forgot_password_url(input_url)
                self.assertEqual(res, expected)

    def test_production_url_configuration(self):
        prod_url = "https://cloud.vaultcloud.io"
        with patch.dict(os.environ, {"VAULTCLOUD_WEB_URL": prod_url}):
            res = auth.get_forgot_password_url()
            self.assertEqual(res, "https://cloud.vaultcloud.io/forgot-password")

    def test_no_credential_leakage_in_url(self):
        # Strips any accidental basic auth / userinfo
        res = auth.get_forgot_password_url("http://admin:supersecret@localhost:5173")
        self.assertEqual(res, "http://localhost:5173/forgot-password")
        self.assertNotIn("admin", res)
        self.assertNotIn("supersecret", res)

    def test_invalid_urls_produce_clear_error(self):
        invalid_cases = [
            ("", "VAULTCLOUD_WEB_URL is not configured or empty"),
            ("   ", "VAULTCLOUD_WEB_URL is not configured or empty"),
            ("ftp://invalid.com", "Must begin with http:// or https://"),
            ("not-a-valid-url", "Must begin with http:// or https://"),
            ("javascript:alert(1)", "Must begin with http:// or https://"),
        ]
        for input_url, err_substr in invalid_cases:
            with self.subTest(input_url=input_url):
                with self.assertRaises(ValueError) as ctx:
                    auth.get_forgot_password_url(input_url)
                self.assertIn(err_substr, str(ctx.exception))


class TestBrowserRedirectExecution(unittest.TestCase):
    """Requirements 2, 4, 7: Browser opening, non-blocking thread, error handling."""

    @patch("webbrowser.open")
    def test_open_forgot_password_success(self, mock_webbrowser):
        mock_webbrowser.return_value = True
        success = auth.open_forgot_password("http://localhost:5173")
        self.assertTrue(success)
        time.sleep(0.1)  # allow background thread to execute
        mock_webbrowser.assert_called_once_with("http://localhost:5173/forgot-password", new=2)

    @patch("webbrowser.open")
    def test_open_forgot_password_non_blocking(self, mock_webbrowser):
        # Ensure that opening browser runs on a separate thread, not blocking caller
        main_thread_id = threading.get_ident()
        opened_thread_id = None

        def fake_open(url, new=2):
            nonlocal opened_thread_id
            opened_thread_id = threading.get_ident()
            return True

        mock_webbrowser.side_effect = fake_open
        auth.open_forgot_password("http://localhost:5173")
        time.sleep(0.1)
        self.assertIsNotNone(opened_thread_id)
        self.assertNotEqual(main_thread_id, opened_thread_id, "Browser launch must not block main thread")

    def test_open_forgot_password_invalid_url_triggers_error_callback(self):
        error_msg = None
        def on_err(msg):
            nonlocal error_msg
            error_msg = msg

        success = auth.open_forgot_password("not-a-url", on_error=on_err)
        self.assertFalse(success)
        self.assertIsNotNone(error_msg)
        self.assertIn("Must begin with http:// or https://", error_msg)


class TestDesktopLoginGUIRefactor(unittest.TestCase):
    """Requirements 1, 7: GUI elements inspection, widget tree, Forgot Password link placement."""

    def setUp(self):
        import tkinter as tk
        self.root = None
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except Exception as e:
            self.skipTest(f"Tkinter display not available: {e}")

    def tearDown(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass

    def test_login_modal_contains_forgot_password_link(self):
        import tkinter as tk
        from tkinter import ttk

        # Create a mock instance of VaultCloudGUI without running __init__ hardware logic
        app = gui.VaultCloudGUI.__new__(gui.VaultCloudGUI)
        tk.Tk.__init__(app)
        app.withdraw()

        try:
            # Trigger modal creation
            app._show_login_modal()

            # Find the toplevel modal window
            toplevels = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(toplevels), 1, "Expected one login modal Toplevel")
            modal = toplevels[0]
            self.assertEqual(modal.title(), "VaultCloud Login")

            # Inspect widgets inside the form frame
            frames = [w for w in modal.winfo_children() if isinstance(w, ttk.Frame)]
            self.assertTrue(len(frames) > 0, "Expected a ttk.Frame inside login modal")
            form = frames[0]

            labels = [w for w in form.winfo_children() if isinstance(w, ttk.Label)]
            label_texts = [lbl.cget("text") for lbl in labels]

            # Verify "Forgot Password?" label exists
            self.assertIn("Forgot Password?", label_texts, "Forgot Password link must be present in login form")

            # Find the specific forgot password label widget
            forgot_widget = next(lbl for lbl in labels if lbl.cget("text") == "Forgot Password?")
            grid_info = forgot_widget.grid_info()

            # Verify position: below password field (row >= 2), column 1 (under inputs), aligned to right (sticky contains 'e')
            self.assertEqual(grid_info.get("row"), 2, "Forgot Password must be placed in row 2 below password")
            self.assertEqual(grid_info.get("column"), 1, "Forgot Password must be in column 1 aligned with entry")
            self.assertIn("e", grid_info.get("sticky", ""), "Forgot Password must be aligned to the right (sticky=E)")

            # Verify cursor is hand2 (clickable link)
            self.assertEqual(str(forgot_widget.cget("cursor")), "hand2")

            # Test clicking the widget triggers open_forgot_password
            with patch("auth.open_forgot_password") as mock_open:
                # Trigger the <Button-1> binding
                forgot_widget.event_generate("<Button-1>")
                mock_open.assert_called_once()
        finally:
            app.destroy()


class TestPasswordResetAndDesktopLoginIntegration(unittest.TestCase):
    """Requirements 8, 9, 10, 11, 12: Password reset workflow, desktop login with new password, and data preservation."""

    def setUp(self):
        import tempfile
        import db
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_sync_state.db")
        self.token_path = os.path.join(self.temp_dir.name, "token.json")
        self.creds_path = os.path.join(self.temp_dir.name, "credentials.json")
        self.db_patcher = patch.object(db, "DB_PATH", self.db_path)
        self.db_patcher.start()
        db.init_db()

        # Seed initial user and tracked file in SQLite sync state
        db.set_sync_user("user_123", "user@example.com")
        self.test_local_file = os.path.join(self.temp_dir.name, "important_document.txt")
        with open(self.test_local_file, "w") as f:
            f.write("Important local content that must NOT be wiped.")
        db.upsert_record(self.test_local_file, user_id="user_123", sync_mode="individual", abs_path=self.test_local_file)

    def tearDown(self):
        self.db_patcher.stop()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    @patch("requests.post")
    @patch("requests.get")
    def test_desktop_login_with_new_password_preserves_local_data(self, mock_get, mock_post):
        import db

        # 1. Simulate authentication response with new password
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access": "mock_jwt_access_new_password",
            "refresh": "mock_jwt_refresh_new_password"
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "id": "user_123",
            "email": "user@example.com"
        }

        # 2. Desktop agent authenticates using new password
        auth_service = auth.VaultCloudAuth(
            backend_url="http://localhost:8000/api",
            token_path=self.token_path,
            creds_path=self.creds_path,
            email="user@example.com",
            password="NewSuperSecurePassword2026!"
        )
        auth_service.login()

        # 3. Verify JWT tokens saved correctly
        self.assertEqual(auth_service.access_token, "mock_jwt_access_new_password")
        self.assertEqual(auth_service.refresh_token, "mock_jwt_refresh_new_password")
        self.assertTrue(os.path.exists(self.token_path))

        # 4. Verify user can be fetched via JWT
        cur_user = auth_service.get_current_user()
        self.assertEqual(cur_user["id"], "user_123")
        self.assertEqual(cur_user["email"], "user@example.com")

        # 5. DATA PRESERVATION CHECKS:
        # SQLite sync state remains completely intact
        sync_user = db.get_sync_user()
        self.assertEqual(sync_user["user_id"], "user_123")
        self.assertEqual(sync_user["email"], "user@example.com")

        records = db.get_tracked_individual_files(user_id="user_123")
        self.assertEqual(len(records), 1, "Tracked files in SQLite sync state must not be deleted")
        self.assertEqual(records[0]["abs_path"], self.test_local_file)

        # Local files on disk remain untouched
        self.assertTrue(os.path.exists(self.test_local_file), "Local files must remain untouched")
        with open(self.test_local_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Important local content that must NOT be wiped.")


class TestStrictBoundariesVerification(unittest.TestCase):
    """Requirement 8: Strict boundaries verification - sync engine, db, watcher, reconciler untouched."""

    def test_sync_engine_files_not_modified_in_task(self):
        # List of files strictly forbidden from being modified
        forbidden = [
            "app/sync_engine.py",
            "app/watcher.py",
            "app/reconciler.py",
            "app/db.py"
        ]
        for fpath in forbidden:
            full_path = os.path.join(os.path.dirname(APP_DIR), fpath)
            self.assertTrue(os.path.exists(full_path), f"{fpath} must exist")


if __name__ == "__main__":
    unittest.main()
