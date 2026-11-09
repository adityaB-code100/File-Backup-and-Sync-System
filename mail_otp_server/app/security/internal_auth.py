import secrets
from functools import wraps
from flask import request, jsonify
from app.config import settings

def require_service_secret(f):
    """
    Decorator for Flask routes ensuring request has valid X-Service-Secret header.
    Uses secrets.compare_digest to prevent side-channel timing attacks.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        secret = request.headers.get("X-Service-Secret")
        if not secret:
            return jsonify({"detail": "Missing required X-Service-Secret header."}), 401

        expected_secret = settings.OTP_SERVICE_SECRET
        if not secrets.compare_digest(secret.strip(), expected_secret.strip()):
            return jsonify({"detail": "Invalid service secret."}), 401

        return f(*args, **kwargs)
    return decorated_function

def verify_internal_service_secret(secret: str | None) -> bool:
    """Helper function for testing or manual verification."""
    if not secret:
        return False
    expected_secret = settings.OTP_SERVICE_SECRET
    return secrets.compare_digest(secret.strip(), expected_secret.strip())
