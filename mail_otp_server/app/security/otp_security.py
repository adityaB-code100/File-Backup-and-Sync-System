import hmac
import hashlib
import secrets
from app.config import settings

def generate_secure_otp() -> str:
    """
    Generates a cryptographically strong 6-digit numeric OTP (100000 - 999999).
    Uses Python's secrets module (operating-system CSPRNG).
    """
    return str(secrets.randbelow(900000) + 100000)

def hash_otp(otp: str, recipient: str) -> str:
    """
    Computes HMAC-SHA256 of the OTP bound to the recipient identifier.
    Uses settings.OTP_SERVICE_SECRET as key to prevent offline rainbow table attacks.
    """
    key = settings.OTP_SERVICE_SECRET.encode("utf-8")
    message = f"{recipient.strip().lower()}:{otp.strip()}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()

def verify_otp_hash(stored_hash: str, candidate_otp: str, recipient: str) -> bool:
    """
    Verifies candidate OTP in constant time to prevent timing attacks.
    """
    candidate_hash = hash_otp(candidate_otp, recipient)
    return secrets.compare_digest(stored_hash, candidate_hash)

