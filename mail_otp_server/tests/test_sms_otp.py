def test_sms_otp_send_and_verify_success(client, auth_headers):
    phone = "+14155552671"
    send_resp = client.post(
        "/api/otp/sms/send",
        json={"phone": phone, "purpose": "mobile_verification"},
        headers=auth_headers
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    dev_otp = send_data.get("dev_otp")
    assert dev_otp is not None
    assert len(dev_otp) == 6

    # Verify with correct code
    verify_resp = client.post(
        "/api/otp/sms/verify",
        json={"phone": phone, "otp": dev_otp, "purpose": "mobile_verification"},
        headers=auth_headers
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["valid"] is True
    assert "Phone number verified" in verify_data["message"]

def test_sms_otp_invalid_phone_format(client, auth_headers):
    # Invalid non-E.164 phone
    send_resp = client.post(
        "/api/otp/sms/send",
        json={"phone": "12345", "purpose": "mobile_verification"},
        headers=auth_headers
    )
    assert send_resp.status_code == 422

