import time
import threading
from typing import Dict, Any, Optional, Tuple
from app.config import settings
from app.security.otp_security import generate_secure_otp, hash_otp, verify_otp_hash

class CooldownActiveError(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after

class OTPRecord:
    def __init__(self, otp_hash: str, recipient: str, purpose: str, raw_otp: Optional[str] = None):
        now = time.time()
        self.otp_hash = otp_hash
        self.recipient = recipient.lower().strip()
        self.purpose = purpose
        self.raw_otp = raw_otp  # Only stored if DEBUG/TESTING
        self.attempts = 0
        self.created_at = now
        self.last_sent_at = now
        self.expires_at = now + settings.OTP_EXPIRATION_SECONDS

class OTPService:
    def __init__(self):
        self._store: Dict[str, OTPRecord] = {}
        self._lock = threading.Lock()

    def _make_key(self, channel: str, purpose: str, recipient: str) -> str:
        return f"{channel.lower().strip()}:{purpose.lower().strip()}:{recipient.lower().strip()}"

    def cleanup_expired(self):
        """Removes expired records to prevent unbounded memory growth."""
        now = time.time()
        with self._lock:
            expired_keys = [
                key for key, record in self._store.items()
                if now > record.expires_at
            ]
            for key in expired_keys:
                del self._store[key]

    def create_otp(
        self,
        recipient: str,
        channel: str = "email",
        purpose: str = "registration"
    ) -> Tuple[str, Optional[int]]:
        """
        Creates and stores a cryptographically secure 6-digit OTP.
        Enforces resend cooldown by raising CooldownActiveError.
        Returns: (raw_otp, cooldown_seconds)
        """
        key = self._make_key(channel, purpose, recipient)
        now = time.time()

        with self._lock:
            # Check existing record for rate-limiting cooldown
            existing = self._store.get(key)
            if existing:
                elapsed = now - existing.last_sent_at
                cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
                if elapsed < cooldown:
                    retry_after = int(cooldown - elapsed)
                    raise CooldownActiveError(
                        message=f"Please wait {retry_after} seconds before requesting another code.",
                        retry_after=retry_after
                    )

            raw_otp = generate_secure_otp()
            hashed = hash_otp(raw_otp, recipient)
            dev_otp = raw_otp if (settings.DEBUG or settings.TESTING) else None

            self._store[key] = OTPRecord(
                otp_hash=hashed,
                recipient=recipient,
                purpose=purpose,
                raw_otp=dev_otp
            )

            return raw_otp, None

    def verify_otp(
        self,
        recipient: str,
        candidate_otp: str,
        channel: str = "email",
        purpose: str = "registration"
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Verifies candidate OTP in constant time.
        Enforces expiration and maximum verification attempts.
        Returns: (is_valid, message, remaining_attempts)
        """
        key = self._make_key(channel, purpose, recipient)
        now = time.time()

        with self._lock:
            record = self._store.get(key)
            if not record:
                return False, "No active verification code found or code already used.", None

            # Check expiration
            if now > record.expires_at:
                del self._store[key]
                return False, "Verification code has expired. Please request a new code.", 0

            # Increment attempt counter
            record.attempts += 1

            # Check max attempts exceeded
            if record.attempts > settings.OTP_MAX_ATTEMPTS:
                del self._store[key]
                return False, "Maximum verification attempts exceeded. Code invalidated.", 0

            # Constant-time comparison
            is_valid = verify_otp_hash(record.otp_hash, candidate_otp, recipient)

            if is_valid:
                # Invalidate after successful use (strictly single-use)
                del self._store[key]
                return True, "Verification successful.", None
            else:
                remaining = max(0, settings.OTP_MAX_ATTEMPTS - record.attempts)
                if remaining == 0:
                    del self._store[key]
                    return False, "Invalid code. Maximum attempts exceeded. Code invalidated.", 0
                return False, f"Invalid verification code. {remaining} attempt(s) remaining.", remaining

    def get_dev_otp(self, recipient: str, channel: str = "email", purpose: str = "registration") -> Optional[str]:
        """Returns raw OTP for testing environments only."""
        if not (settings.DEBUG or settings.TESTING):
            return None
        key = self._make_key(channel, purpose, recipient)
        with self._lock:
            record = self._store.get(key)
            return record.raw_otp if record else None

    def clear(self):
        """Clears all in-memory records (used in unit test teardowns)."""
        with self._lock:
            self._store.clear()

otp_service = OTPService()
