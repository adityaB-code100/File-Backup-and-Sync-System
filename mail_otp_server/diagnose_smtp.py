#!/usr/bin/env python3
"""
VaultCloud Mail OTP Server — Safe SMTP Diagnostic Tool

Performs non-destructive diagnostics of the configured SMTP environment:
1. DNS resolution of SMTP_HOST.
2. TCP connectivity to SMTP_PORT.
3. SMTP server greeting / banner check.
4. TLS / STARTTLS or SSL negotiation.
5. SMTP authentication check (passwords/tokens are NEVER printed).
6. Optional real test email (ONLY if --send-test <recipient> is provided).

Usage:
    python diagnose_smtp.py
    python diagnose_smtp.py --send-test you@example.com
"""

import sys
import os
import argparse
from pathlib import Path

# Add mail_otp_server directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.services.smtp_service import smtp_service


def mask_string(val: str, show_prefix: int = 3, show_suffix: int = 3) -> str:
    """Safely masks sensitive identifiers without showing secrets."""
    if not val:
        return "<not set>"
    if show_prefix == 0 and show_suffix == 0:
        return f"*** (len={len(val)})"
    if len(val) <= show_prefix + show_suffix:
        return "***"
    suffix = val[-show_suffix:] if show_suffix > 0 else ""
    return f"{val[:show_prefix]}...{suffix} (len={len(val)})"


def main():
    parser = argparse.ArgumentParser(
        description="Safe diagnostic check for VaultCloud SMTP configuration."
    )
    parser.add_argument(
        "--send-test",
        metavar="RECIPIENT_EMAIL",
        help="Optional: send a single test email to this address if authentication succeeds.",
        default=None,
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  VaultCloud SMTP Safe Diagnostics")
    print("=" * 70)
    print(f"Host:           {settings.SMTP_HOST}")
    print(f"Port:           {settings.SMTP_PORT}")
    print(f"STARTTLS (587): {settings.SMTP_USE_TLS}")
    print(f"SSL (465):      {settings.SMTP_USE_SSL}")
    print(f"Timeout:        {settings.SMTP_TIMEOUT}s")
    print(f"Sender Email:   {settings.SMTP_FROM_EMAIL}")
    print(f"Username:       {mask_string(settings.SMTP_USERNAME, 4, 4)}")
    print(f"Password:       {'[CONFIGURED]' if settings.SMTP_PASSWORD else '[NOT SET]'}")
    print("-" * 70)

    results = smtp_service.run_diagnostics(send_test_to=args.send_test)

    # 1. DNS Resolution
    dns = results["dns_resolution"]
    if dns.get("status") == "PASS":
        print(f"[PASS] 1. DNS Resolution: Host '{settings.SMTP_HOST}' resolved to {dns.get('resolved_ips')}")
    else:
        print(f"[FAIL] 1. DNS Resolution: {dns.get('error')}")

    # 2. TCP Connectivity
    tcp = results["tcp_connectivity"]
    if tcp.get("status") == "PASS":
        print(f"[PASS] 2. TCP Connectivity: Successfully connected in {tcp.get('latency_ms')}ms")
    else:
        print(f"[FAIL] 2. TCP Connectivity: {tcp.get('error')}")

    # 3. Server Greeting
    greeting = results["server_greeting"]
    if greeting.get("status") == "PASS":
        print(f"[PASS] 3. Server Greeting: SMTP server banner confirmed (Status {greeting.get('code')})")
    else:
        print(f"[FAIL] 3. Server Greeting: {greeting.get('error')}")

    # 4. TLS Negotiation
    tls = results["tls_negotiation"]
    if tls.get("status") == "PASS":
        print(f"[PASS] 4. TLS Negotiation: {tls.get('mode')} established successfully")
    elif tls.get("status") == "INFO":
        print(f"[INFO] 4. TLS Negotiation: {tls.get('mode')}")
    else:
        print(f"[FAIL] 4. TLS Negotiation: {tls.get('error')}")

    # 5. Authentication
    auth = results["authentication"]
    if auth.get("status") == "PASS":
        print(f"[PASS] 5. Authentication: Credentials accepted by SMTP server.")
    elif auth.get("status") == "SKIPPED":
        print(f"[SKIP] 5. Authentication: {auth.get('reason')}")
    else:
        print(f"[FAIL] 5. Authentication: {auth.get('error')}")
        if auth.get("code"):
            print(f"       SMTP Response Code: {auth.get('code')}")

    # 6. Test Email
    test_em = results["test_email"]
    if test_em.get("status") == "PASS":
        print(f"[PASS] 6. Test Email: Delivered successfully to '{test_em.get('recipient')}'")
    elif test_em.get("status") == "FAIL":
        print(f"[FAIL] 6. Test Email: Delivery failed: {test_em.get('error')}")
    else:
        print("[SKIP] 6. Test Email: Not requested (use --send-test <email> to test)")

    print("-" * 70)

    # Summary
    all_passed = (
        dns.get("status") == "PASS"
        and tcp.get("status") == "PASS"
        and greeting.get("status") == "PASS"
        and tls.get("status") in ("PASS", "INFO")
        and auth.get("status") == "PASS"
    )

    if all_passed:
        print("RESULT: All core SMTP checks PASSED. Service is ready for OTP dispatch.")
        sys.exit(0)
    else:
        print("RESULT: One or more SMTP checks FAILED. Review configuration above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
