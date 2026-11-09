def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "VaultCloud Mail & OTP Server"

def test_missing_auth_header(client):
    response = client.post(
        "/api/otp/email/send",
        json={"email": "alice@example.com", "purpose": "registration"}
    )
    assert response.status_code == 401
    assert "Missing required X-Service-Secret" in response.json()["detail"]

def test_invalid_auth_header(client):
    response = client.post(
        "/api/otp/email/send",
        json={"email": "alice@example.com", "purpose": "registration"},
        headers={"X-Service-Secret": "wrong-secret-token"}
    )
    assert response.status_code == 401
    assert "Invalid service secret" in response.json()["detail"]

def test_send_and_verify_email_otp_success(client, auth_headers):
    email = "alice@example.com"
    send_resp = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    dev_otp = send_data.get("dev_otp")
    assert dev_otp is not None
    assert len(dev_otp) == 6
    assert dev_otp.isdigit()

    # Verify with correct OTP
    verify_resp = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": dev_otp, "purpose": "registration"},
        headers=auth_headers
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is True
    assert "verified" in verify_data["message"].lower()

def test_verify_email_otp_invalid_code(client, auth_headers):
    email = "bob@example.com"
    send_resp = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    assert send_resp.status_code == 200

    # Submit bad OTP
    verify_resp = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": "000000", "purpose": "registration"},
        headers=auth_headers
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is False
    assert "Invalid" in verify_data["message"]
    assert verify_data["remaining_attempts"] == 4

def test_otp_is_single_use(client, auth_headers):
    email = "charlie@example.com"
    send_resp = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    dev_otp = send_resp.json()["dev_otp"]

    # First verify succeeds
    v1 = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": dev_otp, "purpose": "registration"},
        headers=auth_headers
    )
    assert v1.json()["valid"] is True

    # Second verify with same OTP fails (single-use)
    v2 = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": dev_otp, "purpose": "registration"},
        headers=auth_headers
    )
    assert v2.json()["valid"] is False
    assert "already used" in v2.json()["message"]


# ─── Mocked SMTP Integration & Error Handling Tests ───────────────────────────

from unittest.mock import patch, MagicMock
import socket
import smtplib
from app.services.smtp_service import (
    SMTPService,
    SMTPAuthError,
    SMTPDnsError,
    SMTPTimeoutError,
    SMTPConnectionError,
    SMTPTlsError,
    SMTPConfigurationError
)
from app.config import settings


def test_smtp_port_587_starttls_connection():
    """Verify Port 587 uses smtplib.SMTP, calls ehlo(), starttls(), and re-ehlo()."""
    with patch("socket.getaddrinfo") as mock_dns, \
         patch("smtplib.SMTP") as mock_smtp:
        
        mock_dns.return_value = [("AF_INET", "SOCK_STREAM", 0, "", ("1.2.3.4", 587))]
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance
        mock_instance.ehlo.return_value = (250, b"OK")
        mock_instance.starttls.return_value = (220, b"Ready for TLS")

        service = SMTPService()
        service.host = "smtp.example.com"
        service.port = 587
        service.use_tls = True
        service.use_ssl = False
        service.username = "testuser"
        service.password = "secretpass"

        conn = service.create_connection()
        assert conn == mock_instance

        # Verify call order: SMTP -> ehlo -> starttls -> ehlo -> login
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=service.timeout)
        assert mock_instance.ehlo.call_count >= 2
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("testuser", "secretpass")


def test_smtp_port_465_ssl_connection():
    """Verify Port 465 uses smtplib.SMTP_SSL, calls ehlo(), and does NOT call starttls()."""
    with patch("socket.getaddrinfo") as mock_dns, \
         patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
        
        mock_dns.return_value = [("AF_INET", "SOCK_STREAM", 0, "", ("1.2.3.4", 465))]
        mock_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_instance
        mock_instance.ehlo.return_value = (250, b"OK")

        service = SMTPService()
        service.host = "smtp.example.com"
        service.port = 465
        service.use_tls = False
        service.use_ssl = True
        service.username = "testuser"
        service.password = "secretpass"

        conn = service.create_connection()
        assert conn == mock_instance

        mock_smtp_ssl.assert_called_once()
        mock_instance.ehlo.assert_called_once()
        assert not hasattr(mock_instance, "starttls") or mock_instance.starttls.call_count == 0
        mock_instance.login.assert_called_once_with("testuser", "secretpass")


def test_smtp_auth_error_returns_502(client, auth_headers):
    """Verify SMTPAuthError returns HTTP 502 with sanitized message."""
    orig_testing = settings.TESTING
    settings.TESTING = False
    try:
        with patch("app.services.smtp_service.smtp_service.send_email_otp") as mock_send:
            mock_send.side_effect = SMTPAuthError("SMTP authentication rejected.")
            resp = client.post(
                "/api/otp/email/send",
                json={"email": "badauth@example.com", "purpose": "registration"},
                headers=auth_headers
            )
            assert resp.status_code == 502
            assert "authentication rejected" in resp.json()["detail"].lower()
    finally:
        settings.TESTING = orig_testing


def test_smtp_dns_error_returns_503(client, auth_headers):
    """Verify SMTPDnsError returns HTTP 503 with sanitized message."""
    orig_testing = settings.TESTING
    settings.TESTING = False
    try:
        with patch("app.services.smtp_service.smtp_service.send_email_otp") as mock_send:
            mock_send.side_effect = SMTPDnsError("Could not resolve mail server host.")
            resp = client.post(
                "/api/otp/email/send",
                json={"email": "dnsfail@example.com", "purpose": "registration"},
                headers=auth_headers
            )
            assert resp.status_code == 503
            assert "resolve mail server" in resp.json()["detail"].lower()
    finally:
        settings.TESTING = orig_testing


def test_smtp_timeout_returns_504(client, auth_headers):
    """Verify SMTPTimeoutError returns HTTP 504 with sanitized message."""
    orig_testing = settings.TESTING
    settings.TESTING = False
    try:
        with patch("app.services.smtp_service.smtp_service.send_email_otp") as mock_send:
            mock_send.side_effect = SMTPTimeoutError("Connection timed out.")
            resp = client.post(
                "/api/otp/email/send",
                json={"email": "timeout@example.com", "purpose": "registration"},
                headers=auth_headers
            )
            assert resp.status_code == 504
            assert "timed out" in resp.json()["detail"].lower()
    finally:
        settings.TESTING = orig_testing


def test_production_simulation_disabled_when_unconfigured():
    """Verify production (TESTING=False) never falls back to simulation and raises SMTPConfigurationError."""
    orig_testing = settings.TESTING
    settings.TESTING = False
    try:
        service = SMTPService()
        service.username = ""
        service.password = ""
        try:
            service.send_email_otp("alice@example.com", "123456", "registration")
            assert False, "Should have raised SMTPConfigurationError"
        except SMTPConfigurationError as e:
            assert "Cannot deliver email in production" in str(e)
    finally:
        settings.TESTING = orig_testing


