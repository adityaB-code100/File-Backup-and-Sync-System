import socket
import ssl
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, Tuple
from app.config import settings

logger = logging.getLogger(__name__)


# ─── Custom SMTP Exceptions ───────────────────────────────────────────────────

class SMTPBaseError(Exception):
    """Base exception for SMTP errors."""
    def __init__(self, message: str, code: str = "SMTP_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class SMTPConfigurationError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_CONFIG_ERROR")


class SMTPDnsError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_DNS_ERROR")


class SMTPConnectionError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_CONNECTION_ERROR")


class SMTPTimeoutError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_TIMEOUT")


class SMTPTlsError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_TLS_ERROR")


class SMTPAuthError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_AUTH_ERROR")


class SMTPSenderRejectedError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_SENDER_REJECTED")


class SMTPRecipientRejectedError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_RECIPIENT_REJECTED")


class SMTPDisconnectionError(SMTPBaseError):
    def __init__(self, message: str):
        super().__init__(message, code="SMTP_DISCONNECTED")


# ─── SMTP Service ─────────────────────────────────────────────────────────────

class SMTPService:
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.use_tls = settings.SMTP_USE_TLS
        self.use_ssl = settings.SMTP_USE_SSL
        self.timeout = settings.SMTP_TIMEOUT
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME

    def _clean_password(self) -> str:
        """
        Normalizes passwords:
        - Strips leading/trailing whitespace.
        - Strips spaces if formatted as a 16-char Google App Password (4x4 with spaces = 19 chars).
        """
        if not self.password:
            return ""
        pwd = self.password.strip()
        # Google App Password check: 16 alphanumeric characters separated by 3 spaces
        if len(pwd) == 19 and pwd.count(" ") == 3:
            candidate = pwd.replace(" ", "")
            if candidate.isalnum():
                return candidate
        return pwd

    def _render_html(self, email: str, otp: str, purpose: str) -> str:
        purpose_titles = {
            "registration": "Complete Your Account Registration",
            "password_reset": "Reset Your VaultCloud Password",
            "email_change": "Verify Your New Email Address",
        }
        title = purpose_titles.get(purpose, "Your Verification Code")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f1f5f9;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #0b0f19; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background-color: #111827; border: 1px solid #1f2937; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5);" cellspacing="0" cellpadding="0" border="0">
          <tr>
            <td style="background: linear-gradient(135deg, #2563eb, #7c3aed); padding: 32px 24px; text-align: center;">
              <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">VaultCloud</h1>
              <p style="margin: 6px 0 0 0; color: #e0e7ff; font-size: 13px; font-weight: 500;">Secure File Backup & Synchronization</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 36px 32px;">
              <h2 style="margin: 0 0 14px 0; color: #f9fafb; font-size: 20px; font-weight: 700;">{title}</h2>
              <p style="margin: 0 0 24px 0; color: #9ca3af; font-size: 14px; line-height: 1.6;">
                Use the verification code below to proceed. For security reasons, this single-use code will expire in <strong>5 minutes</strong>.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin: 28px 0;">
                <tr>
                  <td align="center" style="background-color: #1f2937; border: 2px dashed #3b82f6; border-radius: 12px; padding: 22px;">
                    <div style="font-family: 'Courier New', Courier, monospace; font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #60a5fa; text-shadow: 0 0 12px rgba(96,165,250,0.4);">
                      {otp}
                    </div>
                  </td>
                </tr>
              </table>
              <div style="background-color: rgba(239, 68, 68, 0.08); border-left: 3px solid #ef4444; padding: 12px 16px; border-radius: 6px; margin-bottom: 24px;">
                <p style="margin: 0; color: #fca5a5; font-size: 12.5px; line-height: 1.5;">
                  <strong>Security Reminder:</strong> Never share this code with anyone. VaultCloud personnel will never ask for your verification code.
                </p>
              </div>
              <p style="margin: 0; color: #6b7280; font-size: 13px; line-height: 1.5;">
                If you did not request this verification code, please ignore this email or review your account security immediately.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding: 20px 32px; background-color: #0d131f; border-top: 1px solid #1f2937; text-align: center;">
              <p style="margin: 0; color: #4b5563; font-size: 12px;">
                &copy; VaultCloud Security Platform. Zero-Knowledge Architecture.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    def create_connection(self) -> smtplib.SMTP:
        """
        Creates, negotiates TLS/SSL, and authenticates an SMTP connection.
        Handles:
        - Port 465 (or use_ssl=True): smtplib.SMTP_SSL
        - Port 587 (or use_tls=True): smtplib.SMTP + STARTTLS
        - Port 25: smtplib.SMTP
        - Disconnection recovery: detects provider disconnection on invalid credentials.
        """
        if not self.host:
            raise SMTPConfigurationError("SMTP host is not configured.")

        # 1. DNS Resolution check
        try:
            socket.getaddrinfo(self.host, self.port)
        except socket.gaierror as e:
            logger.error(f"DNS resolution failed for SMTP host '{self.host}': {e}")
            raise SMTPDnsError(f"Could not resolve SMTP server address '{self.host}'.") from e
        except Exception as e:
            raise SMTPConnectionError(f"Network error resolving SMTP server '{self.host}': {e}") from e

        server: Optional[smtplib.SMTP] = None

        try:
            # 2. Establish connection: SSL vs plain/STARTTLS
            if self.port == 465 or self.use_ssl:
                ssl_context = ssl.create_default_context()
                try:
                    server = smtplib.SMTP_SSL(
                        self.host,
                        self.port,
                        timeout=self.timeout,
                        context=ssl_context
                    )
                    server.ehlo()
                except ssl.SSLError as e:
                    raise SMTPTlsError(f"SSL handshake failed on port {self.port}: {e}") from e
                except (socket.timeout, TimeoutError) as e:
                    raise SMTPTimeoutError(f"Connection to {self.host}:{self.port} timed out.") from e
                except ConnectionRefusedError as e:
                    raise SMTPConnectionError(f"Connection refused by {self.host}:{self.port}.") from e
                except smtplib.SMTPServerDisconnected as e:
                    raise SMTPDisconnectionError(f"SMTP server at {self.host}:{self.port} closed connection prematurely.") from e
            else:
                try:
                    server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                    server.ehlo()
                except (socket.timeout, TimeoutError) as e:
                    raise SMTPTimeoutError(f"Connection to {self.host}:{self.port} timed out.") from e
                except ConnectionRefusedError as e:
                    raise SMTPConnectionError(f"Connection refused by {self.host}:{self.port}.") from e
                except smtplib.SMTPServerDisconnected as e:
                    raise SMTPDisconnectionError(f"SMTP server at {self.host}:{self.port} closed connection prematurely.") from e

                # 3. Upgrade with STARTTLS if enabled
                if self.use_tls:
                    ssl_context = ssl.create_default_context()
                    try:
                        server.starttls(context=ssl_context)
                        # RFC 3207: Client MUST re-issue EHLO after successful STARTTLS
                        server.ehlo()
                    except ssl.SSLError as e:
                        raise SMTPTlsError(f"TLS negotiation failed on port {self.port}: {e}") from e
                    except smtplib.SMTPResponseException as e:
                        err_msg = e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
                        raise SMTPTlsError(f"STARTTLS rejected by server ({e.smtp_code}): {err_msg}") from e
                    except smtplib.SMTPServerDisconnected as e:
                        raise SMTPDisconnectionError("SMTP server closed connection during TLS negotiation.") from e

            # 4. Authenticate if username and password are provided
            clean_pwd = self._clean_password()
            if self.username and clean_pwd:
                try:
                    server.login(self.username, clean_pwd)
                except smtplib.SMTPAuthenticationError as e:
                    logger.error(f"SMTP authentication rejected for user '{self.username}': code {e.smtp_code}")
                    raise SMTPAuthError("SMTP authentication rejected. Please verify your email and app password.") from e
                except smtplib.SMTPServerDisconnected as e:
                    # Providers like Google abruptly close TCP socket when authentication fails (535 BadCredentials),
                    # causing smtplib's multi-mechanism fallback loop to raise SMTPServerDisconnected.
                    logger.error(f"SMTP server closed connection during authentication: {e}")
                    raise SMTPAuthError("SMTP authentication failed: server closed connection (invalid credentials or account locked).") from e
                except Exception as e:
                    logger.error(f"Unexpected error during SMTP authentication: {e}")
                    raise SMTPAuthError(f"SMTP authentication failed: {str(e)}") from e

            return server

        except Exception:
            if server:
                try:
                    server.close()
                except Exception:
                    pass
            raise

    def send_email_otp(self, to_email: str, otp: str, purpose: str = "registration") -> bool:
        """
        Sends HTML + plain text email containing the OTP code.
        Rules:
        - In testing mode (settings.TESTING == True), logs action and returns True.
        - In production, NEVER falls back to simulation: raises if unconfigured or failed.
        - Does NOT log OTP values.
        """
        to_email = to_email.strip().lower()

        # Testing/simulation mode: only active when explicitly configured in settings.TESTING
        if settings.TESTING:
            logger.info(
                f"[SIMULATED SMTP] Delivered OTP to '{to_email}' (purpose: {purpose}). "
                "TESTING mode active."
            )
            return True

        # Production check: fail fast if unconfigured
        if not self.username or not self.password:
            raise SMTPConfigurationError(
                "SMTP credentials are not configured. Cannot deliver email in production."
            )

        purpose_titles = {
            "registration": "VaultCloud: Your Registration Verification Code",
            "password_reset": "VaultCloud: Your Password Reset Code",
            "email_change": "VaultCloud: Your Email Verification Code",
        }
        subject = purpose_titles.get(purpose, "VaultCloud Verification Code")
        plain_text = (
            f"Hello,\n\n"
            f"Your VaultCloud verification code for {purpose.replace('_', ' ')} is:\n\n"
            f"    {otp}\n\n"
            f"This code will expire in 5 minutes.\n"
            f"Never share this code with anyone.\n"
        )
        html_content = self._render_html(to_email, otp, purpose)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        server = None
        try:
            server = self.create_connection()
            senderrs = server.sendmail(self.from_email, [to_email], msg.as_string())
            if senderrs:
                logger.error(f"Failed to deliver to recipient '{to_email}': {senderrs}")
                raise SMTPRecipientRejectedError(f"Recipient address '{to_email}' was rejected by mail server.")
            
            logger.info(f"Successfully sent OTP email to {to_email}")
            return True

        except smtplib.SMTPSenderRefused as e:
            logger.error(f"Sender address '{self.from_email}' rejected: {e}")
            raise SMTPSenderRejectedError(f"Sender address '{self.from_email}' was rejected by mail server.") from e
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"Recipient address '{to_email}' rejected: {e}")
            raise SMTPRecipientRejectedError(f"Recipient address '{to_email}' was rejected by mail server.") from e
        except smtplib.SMTPDataError as e:
            logger.error(f"SMTP data rejected: {e}")
            raise SMTPBaseError(f"Email content rejected by mail server: {e}") from e
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass

    def run_diagnostics(self, send_test_to: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes safe diagnostic checks against the configured SMTP provider.
        Never prints or returns credentials or complete authentication tokens.
        """
        results: Dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "use_tls": self.use_tls,
            "use_ssl": self.use_ssl,
            "timeout": self.timeout,
            "from_email": self.from_email,
            "username_configured": bool(self.username),
            "password_configured": bool(self.password),
            "dns_resolution": {"status": "PENDING"},
            "tcp_connectivity": {"status": "PENDING"},
            "server_greeting": {"status": "PENDING"},
            "tls_negotiation": {"status": "PENDING"},
            "authentication": {"status": "PENDING"},
            "test_email": {"status": "SKIPPED"},
        }

        # 1. DNS Resolution
        try:
            addr_info = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
            resolved_ips = list({item[4][0] for item in addr_info})
            results["dns_resolution"] = {
                "status": "PASS",
                "resolved_ips": resolved_ips,
            }
        except Exception as e:
            results["dns_resolution"] = {"status": "FAIL", "error": str(e)}
            return results

        # 2. TCP Connectivity
        import time
        start_time = time.time()
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            latency_ms = round((time.time() - start_time) * 1000, 2)
            sock.close()
            results["tcp_connectivity"] = {
                "status": "PASS",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            results["tcp_connectivity"] = {"status": "FAIL", "error": str(e)}
            return results

        # 3. Server Greeting & TLS Negotiation & Auth
        server = None
        try:
            if self.port == 465 or self.use_ssl:
                ssl_ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ssl_ctx)
                code, msg = server.ehlo()
                results["server_greeting"] = {
                    "status": "PASS",
                    "code": code,
                }
                results["tls_negotiation"] = {
                    "status": "PASS",
                    "mode": "SSL (Port 465)",
                    "cipher": server.sock.cipher() if server.sock else None,
                }
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                code, msg = server.ehlo()
                results["server_greeting"] = {
                    "status": "PASS",
                    "code": code,
                }
                if self.use_tls:
                    ssl_ctx = ssl.create_default_context()
                    server.starttls(context=ssl_ctx)
                    code, msg = server.ehlo()
                    results["tls_negotiation"] = {
                        "status": "PASS",
                        "mode": "STARTTLS (Port 587)",
                        "cipher": server.sock.cipher() if server.sock else None,
                    }
                else:
                    results["tls_negotiation"] = {
                        "status": "INFO",
                        "mode": "Plaintext (No TLS)",
                    }

            # 4. Authentication check
            clean_pwd = self._clean_password()
            if self.username and clean_pwd:
                try:
                    server.login(self.username, clean_pwd)
                    results["authentication"] = {
                        "status": "PASS",
                        "message": "Authentication successful.",
                    }
                except smtplib.SMTPAuthenticationError as ae:
                    results["authentication"] = {
                        "status": "FAIL",
                        "code": ae.smtp_code,
                        "error": "Username or password rejected by server (BadCredentials).",
                    }
                except smtplib.SMTPServerDisconnected:
                    results["authentication"] = {
                        "status": "FAIL",
                        "error": "Server closed connection during auth (credentials rejected).",
                    }
            else:
                results["authentication"] = {
                    "status": "SKIPPED",
                    "reason": "Username or password not configured.",
                }

            # 5. Optional real test email (only when explicitly requested)
            if send_test_to and results["authentication"].get("status") == "PASS":
                try:
                    test_msg = MIMEText("VaultCloud SMTP Diagnostic Test Email.", "plain", "utf-8")
                    test_msg["Subject"] = "VaultCloud SMTP Diagnostic"
                    test_msg["From"] = f"{self.from_name} <{self.from_email}>"
                    test_msg["To"] = send_test_to
                    server.sendmail(self.from_email, [send_test_to], test_msg.as_string())
                    results["test_email"] = {
                        "status": "PASS",
                        "recipient": send_test_to,
                    }
                except Exception as te:
                    results["test_email"] = {
                        "status": "FAIL",
                        "error": str(te),
                    }

        except Exception as e:
            if results["server_greeting"]["status"] == "PENDING":
                results["server_greeting"] = {"status": "FAIL", "error": str(e)}
            elif results["tls_negotiation"]["status"] == "PENDING":
                results["tls_negotiation"] = {"status": "FAIL", "error": str(e)}
            elif results["authentication"]["status"] == "PENDING":
                results["authentication"] = {"status": "FAIL", "error": str(e)}
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    try:
                        server.close()
                    except Exception:
                        pass

        return results


smtp_service = SMTPService()
