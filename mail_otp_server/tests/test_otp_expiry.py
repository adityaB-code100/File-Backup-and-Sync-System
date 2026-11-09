import time
from app.services.otp_service import otp_service

def test_otp_expiry(client, auth_headers):
    email = "expiring@example.com"
    send_resp = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    dev_otp = send_resp.json()["dev_otp"]

    # Manually backdate the expires_at timestamp to simulate 5 minutes passing
    key = otp_service._make_key("email", "registration", email)
    with otp_service._lock:
        record = otp_service._store[key]
        record.expires_at = time.time() - 10

    # Attempt verification with expired code
    verify_resp = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": dev_otp, "purpose": "registration"},
        headers=auth_headers
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is False
    assert "expired" in verify_data["message"].lower()

