import logging
from app.config import settings

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.verify_service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        self.from_phone = settings.TWILIO_FROM_PHONE
        self._client = None

    def _get_client(self):
        if self._client is None and self.account_sid and self.auth_token:
            try:
                from twilio.rest import Client
                self._client = Client(self.account_sid, self.auth_token)
            except Exception as e:
                logger.warning(f"Could not initialize Twilio client: {e}")
                self._client = None
        return self._client

    def send_sms_otp(self, to_phone: str, otp: str, purpose: str = "mobile_verification") -> bool:
        """
        Sends OTP via Twilio SMS / Verify Service.
        Falls back safely to simulation mode if unconfigured or in testing.
        """
        client = self._get_client()

        if not client or settings.TESTING or not self.account_sid or self.account_sid.startswith("ACXXXXXXXX"):
            logger.info(
                f"[SIMULATED SMS] Delivered OTP '{otp}' to phone '{to_phone}' (purpose: {purpose}). "
                "Twilio unconfigured or in test mode."
            )
            return True

        try:
            body_text = f"Your VaultCloud verification code is: {otp}. Valid for 5 minutes. Do not share this code."
            # If Verify Service SID is provided, send through Twilio Verify or Messages
            if self.from_phone:
                client.messages.create(
                    to=to_phone,
                    from_=self.from_phone,
                    body=body_text
                )
            elif self.verify_service_sid:
                client.verify.v2.services(self.verify_service_sid).verifications.create(
                    to=to_phone,
                    channel="sms"
                )
            else:
                client.messages.create(
                    to=to_phone,
                    body=body_text
                )
            logger.info(f"Successfully sent SMS OTP to {to_phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send SMS OTP to {to_phone}: {e}")
            raise

twilio_service = TwilioService()

