# VaultCloud Mail & OTP Microservice (Flask)

Standalone internal microservice responsible for generating, sending, rate-limiting, and verifying One-Time Passwords (OTP) via SMTP (email) and Twilio (SMS).

---

## Features
- **Flask 3.0** lightweight and battle-tested architecture with Flask-CORS.
- **Cryptographic OTP Generation**: 6-digit numeric codes generated with `secrets` module CSPRNG.
- **HMAC-SHA256 Salted Storage**: Plaintext OTPs are never stored in memory or persisted to databases. The in-memory cache stores `HMAC-SHA256(key=OTP_SERVICE_SECRET, msg=recipient:otp)`.
- **Constant-Time Verification**: Uses `secrets.compare_digest` to prevent timing attacks.
- **Security Limits**:
  - 5-minute expiration (TTL).
  - 60-second resend cooldown (HTTP 429).
  - 5 maximum verification attempts before code is invalidated.
  - Strict single-use invalidation upon verification.
- **Service Protection**: Internal endpoints require the `X-Service-Secret` header matching `OTP_SERVICE_SECRET`.
- **E.164 Phone Validation**: Strict validation for international mobile numbers.
- **HTML + Plaintext Email**: Beautifully styled, responsive HTML emails with dark mode aesthetics and security warnings.
- **Mock / Simulation Fallback**: Graceful local development and automated CI testing mode when SMTP/Twilio credentials are absent.

---

## Directory Layout
```text
mail_otp_server/
├── app/
│   ├── config.py             # Environment configuration
│   ├── main.py               # Flask application entry point & blueprints
│   ├── routes/
│   │   ├── email_routes.py   # /api/otp/email/send & /verify
│   │   └── sms_routes.py     # /api/otp/sms/send & /verify
│   ├── schemas/
│   │   └── otp_schemas.py    # Pydantic validation models & E.164 validators
│   ├── security/
│   │   ├── internal_auth.py  # X-Service-Secret decorator check
│   │   └── otp_security.py   # CSPRNG OTP generation & HMAC-SHA256 hashing
│   └── services/
│       ├── otp_service.py    # In-memory thread-safe OTP lifecycle engine
│       ├── smtp_service.py   # SMTP email sender with HTML template
│       └── twilio_service.py # Twilio Verify & SMS dispatcher
├── tests/
│   ├── conftest.py           # Test fixtures using Flask test_client
│   ├── test_email_otp.py
│   ├── test_sms_otp.py
│   ├── test_otp_expiry.py
│   └── test_rate_limiting.py
├── .env.example
├── requirements.txt
├── run.py
├── run_tests.py
└── README.md
```

---

## Endpoints

| Method | Path | Description | Protected by Secret |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service uptime and health status | No |
| `POST` | `/api/otp/email/send` | Request 6-digit email OTP | Yes (`X-Service-Secret`) |
| `POST` | `/api/otp/email/verify` | Verify 6-digit email OTP | Yes (`X-Service-Secret`) |
| `POST` | `/api/otp/sms/send` | Request 6-digit SMS OTP | Yes (`X-Service-Secret`) |
| `POST` | `/api/otp/sms/verify` | Verify 6-digit SMS OTP | Yes (`X-Service-Secret`) |

---

## Running the Service

```bash
cd mail_otp_server
python run.py
```
Or with Flask CLI:
```bash
flask --app app.main run --port 8001
```

## Running Tests

```bash
python mail_otp_server/run_tests.py
```
