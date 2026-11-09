import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class OTPClient:
    def __init__(self):
        self.server_url = getattr(settings, 'OTP_SERVER_URL', 'http://127.0.0.1:8001').rstrip('/')
        self.service_secret = getattr(settings, 'OTP_SERVICE_SECRET', 'vaultcloud-internal-otp-secret-key-32b')
        self.timeout = 5.0  # seconds

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "X-Service-Secret": self.service_secret
        }

    def send_email_otp(self, email: str, purpose: str = "registration") -> dict:
        url = f"{self.server_url}/api/otp/email/send"
        payload = {"email": email.strip().lower(), "purpose": purpose}
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            if resp.status_code == 429:
                data = resp.json()
                detail = data.get("detail", {})
                retry_after = detail.get("retry_after", 60) if isinstance(detail, dict) else 60
                return {
                    "success": False,
                    "error": f"Please wait {retry_after} seconds before requesting another code.",
                    "code": "COOLDOWN_ACTIVE",
                    "retry_after": retry_after
                }
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"OTP server request failed: {e}. Checking fallback mode...")
            # Fallback for dev / isolated unit tests without microservice running
            if getattr(settings, 'DEBUG', False) or getattr(settings, 'TESTING', False):
                logger.info(f"[DEV FALLBACK] Simulated OTP dispatch to {email} for {purpose}.")
                return {"success": True, "message": "Verification code dispatched.", "dev_otp": "123456"}
            raise RuntimeError(f"Could not connect to OTP service: {str(e)}")

    def verify_email_otp(self, email: str, otp: str, purpose: str = "registration") -> dict:
        url = f"{self.server_url}/api/otp/email/verify"
        payload = {"email": email.strip().lower(), "otp": otp.strip(), "purpose": purpose}
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"OTP server verify failed: {e}. Checking fallback mode...")
            if getattr(settings, 'DEBUG', False) or getattr(settings, 'TESTING', False):
                if otp.strip() in ("123456", "999999"):
                    return {"valid": True, "message": "Email verified successfully."}
                return {"valid": False, "message": "Invalid verification code.", "remaining_attempts": 3}
            raise RuntimeError(f"Could not connect to OTP service: {str(e)}")

    def send_sms_otp(self, phone: str, purpose: str = "mobile_verification") -> dict:
        url = f"{self.server_url}/api/otp/sms/send"
        payload = {"phone": phone.strip(), "purpose": purpose}
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            if resp.status_code == 429:
                data = resp.json()
                detail = data.get("detail", {})
                retry_after = detail.get("retry_after", 60) if isinstance(detail, dict) else 60
                return {
                    "success": False,
                    "error": f"Please wait {retry_after} seconds before requesting another SMS.",
                    "code": "COOLDOWN_ACTIVE",
                    "retry_after": retry_after
                }
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"OTP server SMS request failed: {e}. Checking fallback mode...")
            if getattr(settings, 'DEBUG', False) or getattr(settings, 'TESTING', False):
                logger.info(f"[DEV FALLBACK] Simulated SMS OTP dispatch to {phone}.")
                return {"success": True, "message": "Verification code dispatched via SMS.", "dev_otp": "123456"}
            raise RuntimeError(f"Could not connect to OTP service: {str(e)}")

    def verify_sms_otp(self, phone: str, otp: str, purpose: str = "mobile_verification") -> dict:
        url = f"{self.server_url}/api/otp/sms/verify"
        payload = {"phone": phone.strip(), "otp": otp.strip(), "purpose": purpose}
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"OTP server SMS verify failed: {e}. Checking fallback mode...")
            if getattr(settings, 'DEBUG', False) or getattr(settings, 'TESTING', False):
                if otp.strip() in ("123456", "999999"):
                    return {"valid": True, "message": "Phone number verified successfully."}
                return {"valid": False, "message": "Invalid SMS verification code.", "remaining_attempts": 3}
            raise RuntimeError(f"Could not connect to OTP service: {str(e)}")

otp_client = OTPClient()

