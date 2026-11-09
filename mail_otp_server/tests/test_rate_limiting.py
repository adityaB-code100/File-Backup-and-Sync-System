def test_cooldown_rate_limiting(client, auth_headers):
    email = "speedy@example.com"
    # First request succeeds
    r1 = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    assert r1.status_code == 200

    # Immediate second request fails with 429
    r2 = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    assert r2.status_code == 429
    err_detail = r2.json()["detail"]
    assert "Please wait" in err_detail["error"]
    assert err_detail["retry_after"] > 0

def test_max_attempts_lockout(client, auth_headers):
    email = "bruteforce@example.com"
    r1 = client.post(
        "/api/otp/email/send",
        json={"email": email, "purpose": "registration"},
        headers=auth_headers
    )
    assert r1.status_code == 200

    # 4 invalid attempts
    for attempt in range(1, 5):
        resp = client.post(
            "/api/otp/email/verify",
            json={"email": email, "otp": "000000", "purpose": "registration"},
            headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert resp.json()["remaining_attempts"] == (5 - attempt)

    # 5th attempt exhausts attempts
    resp5 = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": "000000", "purpose": "registration"},
        headers=auth_headers
    )
    assert resp5.status_code == 200
    assert resp5.json()["valid"] is False
    assert resp5.json()["remaining_attempts"] == 0
    assert "maximum" in resp5.json()["message"].lower()

    # Subsequent attempt fails because OTP is invalidated
    resp6 = client.post(
        "/api/otp/email/verify",
        json={"email": email, "otp": "000000", "purpose": "registration"},
        headers=auth_headers
    )
    assert resp6.status_code == 200
    assert resp6.json()["valid"] is False
    assert "no active verification code" in resp6.json()["message"].lower()

