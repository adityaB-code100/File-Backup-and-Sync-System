import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present in mail_otp_server/ or root
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

class Settings:
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8001"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # Shared secret between Django and this service
    OTP_SERVICE_SECRET: str = os.getenv(
        "OTP_SERVICE_SECRET", "vaultcloud-internal-otp-secret-key-32b"
    )

    # OTP Rules
    OTP_EXPIRATION_SECONDS: int = int(os.getenv("OTP_EXPIRATION_SECONDS", "300"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    OTP_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))

    # SMTP Configuration
    # Supports both SMTP_HOST and SMTP_SERVER
    SMTP_HOST: str = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER") or "smtp.gmail.com"
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "").strip()
    # Explicit TLS (STARTTLS) vs SSL flags
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "True" if os.getenv("SMTP_PORT") != "465" else "False").lower() in ("true", "1", "yes")
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "True" if os.getenv("SMTP_PORT") == "465" else "False").lower() in ("true", "1", "yes")
    SMTP_TIMEOUT: int = int(os.getenv("SMTP_TIMEOUT", "15"))
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "").strip() or os.getenv("SMTP_USERNAME", "").strip() or "noreply@vaultcloud.local"
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "VaultCloud Security")

    # Twilio Configuration
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_VERIFY_SERVICE_SID: str = os.getenv("TWILIO_VERIFY_SERVICE_SID", "")
    TWILIO_FROM_PHONE: str = os.getenv("TWILIO_FROM_PHONE", "")

    # Testing / Simulation mode
    TESTING: bool = os.getenv("TESTING", "False").lower() in ("true", "1", "yes")

settings = Settings()

