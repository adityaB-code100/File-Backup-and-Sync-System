import logging
from datetime import datetime, timezone
from flask import Flask, jsonify
from flask_cors import CORS
from app.config import settings
from app.routes.email_routes import email_bp
from app.routes.sms_routes import sms_bp
from app.services.otp_service import otp_service

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mail_otp_server")

app = Flask(__name__)
CORS(app)

# Register routes
app.register_blueprint(email_bp)
app.register_blueprint(sms_bp)

@app.route("/health", methods=["GET"])
def health_check():
    """
    Public health check endpoint for monitoring uptime.
    """
    otp_service.cleanup_expired()
    return jsonify({
        "status": "ok",
        "service": "VaultCloud Mail & OTP Server",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"
    }), 200

if __name__ == "__main__":
    app.run(
        host=settings.HOST,
        port=settings.PORT,
        debug=settings.DEBUG
    )
