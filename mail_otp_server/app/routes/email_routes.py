import logging
from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from app.schemas.otp_schemas import EmailSendOTPRequest, EmailVerifyOTPRequest
from app.services.otp_service import otp_service, CooldownActiveError
from app.services.smtp_service import (
    smtp_service,
    SMTPBaseError,
    SMTPAuthError,
    SMTPDnsError,
    SMTPTimeoutError,
    SMTPConnectionError,
    SMTPTlsError,
    SMTPRecipientRejectedError,
    SMTPSenderRejectedError,
    SMTPConfigurationError
)
from app.security.internal_auth import require_service_secret
from app.config import settings

logger = logging.getLogger(__name__)

email_bp = Blueprint("email_otp", __name__, url_prefix="/api/otp/email")

def _clean_pydantic_errors(ve: ValidationError):
    return [
        {
            "loc": list(err.get("loc", [])),
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", ""))
        }
        for err in ve.errors()
    ]

@email_bp.route("/send", methods=["POST"])
@require_service_secret
def send_email_otp():
    """
    Generates and dispatches a 6-digit email OTP.
    Protected by X-Service-Secret header.
    Enforces a 60-second cooldown between requests.
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = EmailSendOTPRequest(**data)
    except ValidationError as ve:
        return jsonify({"detail": _clean_pydantic_errors(ve)}), 422

    email_clean = payload.email.lower().strip()
    try:
        raw_otp, _ = otp_service.create_otp(
            recipient=email_clean,
            channel="email",
            purpose=payload.purpose
        )
        # Dispatch via SMTP
        smtp_service.send_email_otp(
            to_email=email_clean,
            otp=raw_otp,
            purpose=payload.purpose
        )

        dev_otp = raw_otp if (settings.DEBUG or settings.TESTING) else None
        return jsonify({
            "success": True,
            "message": "Verification code dispatched to your email.",
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
    except SMTPAuthError as ae:
        logger.error(f"SMTP Auth Error: {ae.message}")
        return jsonify({"detail": "Failed to deliver verification email: mail authentication rejected. Please verify SMTP credentials."}), 502
    except SMTPDnsError as de:
        logger.error(f"SMTP DNS Error: {de.message}")
        return jsonify({"detail": "Failed to deliver verification email: could not resolve mail server host."}), 503
    except SMTPTimeoutError as te:
        logger.error(f"SMTP Timeout Error: {te.message}")
        return jsonify({"detail": "Failed to deliver verification email: mail server timed out."}), 504
    except SMTPConnectionError as ce:
        logger.error(f"SMTP Connection Error: {ce.message}")
        return jsonify({"detail": "Failed to deliver verification email: could not connect to mail server."}), 502
    except SMTPTlsError as tle:
        logger.error(f"SMTP TLS Error: {tle.message}")
        return jsonify({"detail": "Failed to deliver verification email: secure TLS negotiation failed."}), 502
    except (SMTPRecipientRejectedError, SMTPSenderRejectedError) as re:
        logger.error(f"SMTP Address Rejected: {re.message}")
        return jsonify({"detail": f"Failed to deliver verification email: {re.message}"}), 400
    except SMTPConfigurationError as ce:
        logger.error(f"SMTP Config Error: {ce.message}")
        return jsonify({"detail": "Mail delivery is not properly configured on the server."}), 503
    except SMTPBaseError as se:
        logger.error(f"SMTP Error: {se.message}")
        return jsonify({"detail": f"Failed to deliver verification email: {se.message}"}), 502
    except Exception as e:
        logger.error(f"Unhandled error in send_email_otp: {e}", exc_info=True)
        return jsonify({"detail": "Failed to deliver verification email due to an internal server error."}), 500


@email_bp.route("/verify", methods=["POST"])
@require_service_secret
def verify_email_otp():
    """
    Verifies candidate 6-digit email OTP.
    Protected by X-Service-Secret header.
    Single-use: code is invalidated immediately on success or after 5 failed attempts.
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = EmailVerifyOTPRequest(**data)
    except ValidationError as ve:
        return jsonify({"detail": _clean_pydantic_errors(ve)}), 422

    email_clean = payload.email.lower().strip()
    valid, message, remaining = otp_service.verify_otp(
        recipient=email_clean,
        candidate_otp=payload.otp.strip(),
        channel="email",
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
        "message": "Email verified successfully."
    }), 200
