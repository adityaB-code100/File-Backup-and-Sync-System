import logging
import os
import json
import requests
import jwt

# Keyring for secure credential storage (replaces plaintext password in credentials.json).
# Falls back gracefully when keyring is unavailable (CI, headless servers).
try:
    import keyring
    import keyring.errors
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE = "vaultcloud"

logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CANONICAL_TOKEN_PATH = os.path.join(APP_DIR, "token.json")
CANONICAL_CREDS_PATH = os.path.join(APP_DIR, "credentials.json")
LEGACY_ROOT_TOKEN_PATH = os.path.join(os.path.dirname(APP_DIR), "token.json")
LEGACY_ROOT_CREDS_PATH = os.path.join(os.path.dirname(APP_DIR), "credentials.json")

BACKEND_URL = os.getenv("VAULTCLOUD_BACKEND_URL", "http://localhost:8000/api")
VAULTCLOUD_WEB_URL = os.getenv("VAULTCLOUD_WEB_URL", "http://localhost:5173")


def get_forgot_password_url(base_url: str | None = None) -> str:
    """
    Validates and formats the Forgot Password redirect URL.
    - Strips trailing slashes safely.
    - Appends /forgot-password exactly once.
    - Validates scheme (http/https) and host.
    - Strips userinfo/credentials if present.
    """
    raw_url = base_url if base_url is not None else os.getenv("VAULTCLOUD_WEB_URL", VAULTCLOUD_WEB_URL)
    if not raw_url or not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("VAULTCLOUD_WEB_URL is not configured or empty.")

    from urllib.parse import urlparse
    cleaned = raw_url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid VAULTCLOUD_WEB_URL: '{raw_url}'. Must begin with http:// or https:// and include a valid host.")

    path = parsed.path.rstrip("/")
    if path.endswith("/forgot-password"):
        target_path = path
    else:
        target_path = f"{path}/forgot-password"

    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    return f"{parsed.scheme}://{netloc}{target_path}"


def open_forgot_password(base_url: str | None = None, on_error=None) -> bool:
    """
    Opens the system browser to the Forgot Password URL in a non-blocking thread.
    Returns True if browser launch was dispatched, False on validation/launch error.
    """
    import webbrowser
    import threading

    try:
        url = get_forgot_password_url(base_url)
    except Exception as e:
        logger.error(f"Failed to resolve Forgot Password URL: {e}")
        if on_error:
            on_error(str(e))
        return False

    def _open():
        try:
            logger.info(f"Opening browser for password reset: {url}")
            success = webbrowser.open(url, new=2)
            if not success:
                logger.warning(f"webbrowser.open returned False for URL: {url}")
        except Exception as err:
            logger.error(f"Error opening browser: {err}")
            if on_error:
                on_error(f"Could not open browser: {err}")

    threading.Thread(target=_open, daemon=True, name="open_forgot_password_browser").start()
    return True

def _safe_extract_account_info(token_path: str) -> dict | None:
    """Reads unverified token payload to extract account email and user_id without exposing secrets."""
    if not os.path.exists(token_path):
        return None
    try:
        with open(token_path, "r") as f:
            data = json.load(f)
            access = data.get("access")
            if access:
                payload = jwt.decode(access, options={"verify_signature": False})
                return {
                    "email": payload.get("email"),
                    "user_id": payload.get("user_id")
                }
    except Exception:
        pass
    return None

class VaultCloudAuth:
    def __init__(self, backend_url=BACKEND_URL, token_path=None, creds_path=None, email=None, password=None):
        self.backend_url = backend_url.rstrip("/")
        # Always use absolute paths anchored to APP_DIR by default
        self.token_path = os.path.abspath(token_path) if token_path else CANONICAL_TOKEN_PATH
        self.creds_path = os.path.abspath(creds_path) if creds_path else CANONICAL_CREDS_PATH
        self.email_arg = email
        self.password_arg = password
        self.access_token = None
        self.refresh_token = None
        self.current_user = None

        if self.email_arg and self.password_arg:
            logger.info(f"CLI credentials received for '{self.email_arg}'. Forcing fresh authentication.")
            # Do not load cached tokens; force login with provided credentials
        else:
            self._resolve_and_load_tokens()

    def _resolve_and_load_tokens(self):
        """Resolves token location, migrating legacy root tokens if necessary without silent account confusion."""
        canonical_exists = os.path.exists(self.token_path)
        legacy_exists = os.path.exists(LEGACY_ROOT_TOKEN_PATH) and os.path.abspath(self.token_path) != os.path.abspath(LEGACY_ROOT_TOKEN_PATH)

        if not canonical_exists and legacy_exists:
            # Safe migration: adopt legacy root token into canonical location
            legacy_info = _safe_extract_account_info(LEGACY_ROOT_TOKEN_PATH)
            logger.info(f"Migrating session token from root directory to canonical path '{self.token_path}' (Account: {legacy_info.get('email') if legacy_info else 'unknown'}).")
            try:
                with open(LEGACY_ROOT_TOKEN_PATH, "r") as src, open(self.token_path, "w") as dst:
                    dst.write(src.read())
                if os.path.exists(LEGACY_ROOT_CREDS_PATH) and not os.path.exists(self.creds_path):
                    with open(LEGACY_ROOT_CREDS_PATH, "r") as csrc, open(self.creds_path, "w") as cdst:
                        cdst.write(csrc.read())
            except Exception as e:
                logger.warning(f"Could not migrate legacy token: {e}")

        elif canonical_exists and legacy_exists:
            canonical_info = _safe_extract_account_info(self.token_path)
            legacy_info = _safe_extract_account_info(LEGACY_ROOT_TOKEN_PATH)

            can_email = canonical_info.get("email") if canonical_info else None
            leg_email = legacy_info.get("email") if legacy_info else None

            if can_email and leg_email and can_email != leg_email:
                # Discrepancy detected between app/ and root
                # Check if SQLite database is bound to one of them
                try:
                    import db
                    sync_user = db.get_sync_user()
                    if sync_user and sync_user.get("email") == leg_email:
                        logger.info(f"Credential resolution: adopting root token matching active sync database account ({leg_email}).")
                        with open(LEGACY_ROOT_TOKEN_PATH, "r") as src, open(self.token_path, "w") as dst:
                            dst.write(src.read())
                    else:
                        logger.info(f"Using canonical session token for '{can_email}'.")
                except Exception:
                    logger.info(f"Using canonical session token for '{can_email}'.")

        self.load_tokens()

    def load_tokens(self):
        try:
            with open(self.token_path, "r") as f:
                data = json.load(f)
                self.access_token = data.get("access")
                self.refresh_token = data.get("refresh")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save_tokens(self):
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump({
                "access": self.access_token,
                "refresh": self.refresh_token
            }, f)

    def _get_password_from_keyring(self, email: str) -> str | None:
        """Retrieve password from system keyring. Returns None if unavailable."""
        if not _KEYRING_AVAILABLE or not email:
            return None
        try:
            return keyring.get_password(_KEYRING_SERVICE, email)
        except Exception:
            return None

    def _save_password_to_keyring(self, email: str, password: str) -> bool:
        """Store password in system keyring. Returns True on success."""
        if not _KEYRING_AVAILABLE or not email or not password:
            return False
        try:
            keyring.set_password(_KEYRING_SERVICE, email, password)
            return True
        except Exception:
            return False

    def _delete_password_from_keyring(self, email: str) -> None:
        """Remove stored keyring password. Silent on failure."""
        if not _KEYRING_AVAILABLE or not email:
            return
        try:
            keyring.delete_password(_KEYRING_SERVICE, email)
        except Exception:
            pass

    def _load_credentials_from_disk(self) -> tuple[str | None, str | None]:
        """Load email from credentials.json; retrieve password from keyring or legacy field."""
        try:
            with open(self.creds_path, "r") as f:
                creds = json.load(f)
            email = creds.get("email")
            # Attempt keyring first; fall back to legacy plaintext field
            password = self._get_password_from_keyring(email) if email else None
            if not password:
                # Legacy plaintext — migrate transparently, then wipe from disk
                password = creds.get("password")
                if password and email:
                    migrated = self._save_password_to_keyring(email, password)
                    if migrated:
                        # Remove plaintext password from disk
                        self._save_email_config(email)
                        logger.info("Migrated plaintext password to system keyring; removed from credentials file.")
            return email, password
        except (FileNotFoundError, json.JSONDecodeError):
            return None, None

    def _save_email_config(self, email: str) -> None:
        """Persist only the email (no password) to credentials.json."""
        os.makedirs(os.path.dirname(self.creds_path), exist_ok=True)
        with open(self.creds_path, "w") as f:
            json.dump({"email": email}, f)

    def login(self):
        email = self.email_arg
        password = self.password_arg

        if not email or not password:
            email, password = self._load_credentials_from_disk()

        if not email:
            logger.error(
                f"Could not load credentials from '{self.creds_path}'. "
                "Please provide --email and --password."
            )
            email = input("Email: ")
            password = input("Password: ")

        if not password and email:
            password = self._get_password_from_keyring(email)

        if not password:
            password = input(f"Password for {email}: ")

        if email and password:
            # Persist: email to disk (no plaintext password), password to keyring when possible
            self._save_email_config(email)
            saved_to_keyring = self._save_password_to_keyring(email, password)
            if not saved_to_keyring:
                logger.warning(
                    "System keyring unavailable — password not persisted. "
                    "You will be prompted for the password on next launch."
                )

        logger.info(f"→ Authenticating against {self.backend_url}/auth/login/ for account '{email}'...")
        resp = requests.post(f"{self.backend_url}/auth/login/", json={"email": email, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access"]
        self.refresh_token = data["refresh"]
        self.save_tokens()
        self.current_user = None
        
        user_data = self.get_current_user()
        if user_data:
            logger.info(f"Successfully authenticated as: {user_data.get('email')} (User ID: {user_data.get('id')})")
        else:
            logger.info("Successfully authenticated.")

    def do_refresh(self):
        if not self.refresh_token:
            self.login()
            return
            
        logger.info("Refreshing access token...")
        try:
            resp = requests.post(f"{self.backend_url}/auth/refresh/", json={"refresh": self.refresh_token})
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access"]
            if "refresh" in data:
                self.refresh_token = data["refresh"]
            self.save_tokens()
            self.current_user = None
        except requests.RequestException:
            logger.warning("Token refresh failed. Re-authenticating...")
            self.login()

    def get_auth_header(self):
        if not self.access_token:
            self.login()
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_current_user(self) -> dict | None:
        if self.current_user:
            return self.current_user
        if not self.access_token:
            self.login()
        try:
            resp = requests.get(f"{self.backend_url}/auth/me/", headers={"Authorization": f"Bearer {self.access_token}"})
            if resp.status_code == 401:
                self.do_refresh()
                resp = requests.get(f"{self.backend_url}/auth/me/", headers={"Authorization": f"Bearer {self.access_token}"})
            resp.raise_for_status()
            self.current_user = resp.json()
            return self.current_user
        except requests.RequestException as e:
            logger.error(f"Failed to fetch user profile: {e}")
            return None

    def logout(self) -> None:
        """Clear session tokens and in-memory state. Removes keyring entry for remembered account."""
        # Read email before clearing state
        email = None
        if self.current_user:
            email = self.current_user.get("email")
        if not email:
            try:
                with open(self.creds_path, "r") as f:
                    email = json.load(f).get("email")
            except Exception:
                pass

        # Clear in-memory state
        self.access_token = None
        self.refresh_token = None
        self.current_user = None

        # Remove token file
        try:
            if os.path.exists(self.token_path):
                os.remove(self.token_path)
        except Exception as e:
            logger.warning(f"Could not remove token file: {e}")

        # Clear keyring entry so the user is prompted on next launch
        if email:
            self._delete_password_from_keyring(email)

        logger.info("Logged out. Session tokens cleared.")

def get_drive_service(email=None, password=None):
    """
    Returns an instance of VaultCloudAuth instead of Google Drive service.
    Keeps the same function name for backward compatibility until renaming is fully done.
    """
    auth = VaultCloudAuth(email=email, password=password)
    # Eagerly verify credentials and fetch identity
    auth.get_auth_header()
    auth.get_current_user()
    return auth