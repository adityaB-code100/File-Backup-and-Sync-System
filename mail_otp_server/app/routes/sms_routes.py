import logging
from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from app.schemas.otp_schemas import SMSSendOTPRequest, SMSVerifyOTPRequest
from app.services.otp_service import otp_service, CooldownActiveError
from app.services.twilio_service import twilio_service
from app.security.internal_auth import require_service_secret
from app.config import settings

logger = logging.getLogger(__name__)

sms_bp = Blueprint("sms_otp", __name__, url_prefix="/api/otp/sms")

def _clean_pydantic_errors(ve: ValidationError):
    return [
        {
            "loc": list(err.get("loc", [])),
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", ""))
        }
        for err in ve.errors()
    ]

@sms_bp.route("/send", methods=["POST"])
@require_service_secret
def send_sms_otp():
    """
    Generates and dispatches a 6-digit SMS OTP via Twilio.
    Protected by X-Service-Secret header.
    Enforces a 60-second cooldown between requests.
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = SMSSendOTPRequest(**data)
    except ValidationError as ve:
        return jsonify({"detail": _clean_pydantic_errors(ve)}), 422

    phone_clean = payload.phone.strip()
    try:
        raw_otp, _ = otp_service.create_otp(
            recipient=phone_clean,
            channel="sms",
            purpose=payload.purpose
        )
        # Dispatch via Twilio
        twilio_service.send_sms_otp(
            to_phone=phone_clean,
            otp=raw_otp,
            purpose=payload.purpose
        )

        dev_otp = raw_otp if (settings.DEBUG or settings.TESTING) else None
        return jsonify({
            "success": True,
            "message": "Verification code dispatched via SMS.",
            "dev_otp": dev_otp
        }), 200

    except CooldownActiveError as cae:
        return jsonify({
            "detail": {
                "error": cae.message,
                "retry_after": cae.retry_after,
                "code": "COOLDOWN_ACTIVE"
            }
        }), 429
    except Exception as e:
        logger.error(f"Error in send_sms_otp: {e}")
        return jsonify({"detail": f"Failed to deliver SMS verification code: {str(e)}"}), 500


@sms_bp.route("/verify", methods=["POST"])
@require_service_secret
def verify_sms_otp():
    """
    Verifies candidate 6-digit SMS OTP.
    Protected by X-Service-Secret header.
    Single-use: code is invalidated immediately on success or after 5 failed attempts.
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = SMSVerifyOTPRequest(**data)
    except ValidationError as ve:
        return jsonify({"detail": _clean_pydantic_errors(ve)}), 422

    phone_clean = payload.phone.strip()
    valid, message, remaining = otp_service.verify_otp(
        recipient=phone_clean,
        candidate_otp=payload.otp.strip(),
        channel="sms",
        purpose=payload.purpose
    )

    if not valid:
        return jsonify({
            "valid": False,
            "message": message,
            "remaining_attempts": remaining
        }), 200

    return jsonify({
        "valid": True,
        "message": "Phone number verified successfully."
    }), 200
