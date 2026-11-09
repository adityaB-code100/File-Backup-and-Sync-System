import secrets
import hashlib
import logging
import re
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone as dj_timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, PasswordResetToken
from accounts.auth import get_tokens_for_user
from accounts.otp_client import otp_client
from accounts.location_data import validate_location, SUPPORTED_COUNTRIES
from cloud_storage.timezone_utils import make_aware_utc, now_utc
import phonenumbers
import mongoengine as me

logger = logging.getLogger(__name__)

class RegisterView(APIView):
    """
    User Registration:
    Creates an account in unverified status (is_email_verified=False)
    and dispatches a 6-digit OTP to the user's email address via the Mail/OTP service.
    Tokens are NOT issued until the OTP is verified.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        full_name = request.data.get('full_name', '').strip()

        if not email or not password:
            return Response(
                {"error": "Email and password are required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(password) < 8:
            return Response(
                {"error": "Password must be at least 8 characters long.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if password.lower() == email.lower():
            return Response(
                {"error": "Password cannot be the same as your email address.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )
        local_part = email.split('@')[0].lower() if '@' in email else ''
        if local_part and len(local_part) >= 4 and password.lower() == local_part:
            return Response(
                {"error": "Password cannot be your email username.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not password.strip():
            return Response(
                {"error": "Password cannot contain only spaces.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        existing_user = User.objects(email=email).first()
        if existing_user:
            if existing_user.is_email_verified:
                return Response(
                    {"error": "User with this email already exists.", "code": "USER_EXISTS"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                # Existing unverified account: update credentials and resend verification OTP
                user = existing_user
                user.set_password(password)
                if full_name:
                    user.full_name = full_name
                user.save()
        else:
            user = User(
                email=email,
                full_name=full_name,
                is_email_verified=False
            )
            user.set_password(password)
            user.save()

        # Request email OTP from mail_otp_server
        otp_res = otp_client.send_email_otp(email, purpose="registration")

        resp_payload = {
            "message": "Account created. Please enter the 6-digit verification code sent to your email.",
            "email": email,
            "is_email_verified": False,
            "requires_verification": True
        }
        if otp_res.get("dev_otp"):
            resp_payload["dev_otp"] = otp_res["dev_otp"]

        return Response(resp_payload, status=status.HTTP_201_CREATED)


class VerifyEmailOTPView(APIView):
    """
    Verifies the email OTP. On successful registration verification,
    activates the account (is_email_verified=True) and returns session JWT tokens.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp', '').strip()
        purpose = request.data.get('purpose', 'registration')

        if not email or not otp:
            return Response(
                {"error": "Email and OTP code are required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects(email=email).first()
        if not user:
            return Response(
                {"error": "Account not found for this email.", "code": "NOT_FOUND"},
                status=status.HTTP_404_NOT_FOUND
            )

        verify_res = otp_client.verify_email_otp(email, otp, purpose=purpose)
        if not verify_res.get("valid"):
            msg = verify_res.get("message", "Invalid or expired verification code.")
            return Response(
                {"error": msg, "code": "INVALID_OTP", "remaining_attempts": verify_res.get("remaining_attempts")},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark email verified
        user.is_email_verified = True
        user.updated_at = datetime.utcnow()
        user.save()

        # Generate JWT session tokens upon activation
        tokens = get_tokens_for_user(user)

        return Response({
            "message": "Email verified successfully. Account activated.",
            "access": tokens['access'],
            "refresh": tokens['refresh'],
            "user": user.to_dict()
        }, status=status.HTTP_200_OK)


class ResendOTPView(APIView):
    """
    Resends OTP to the requested email or mobile. Enforces 60-second cooldown.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        purpose = request.data.get('purpose', 'registration')

        if not email:
            return Response(
                {"error": "Email address is required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        res = otp_client.send_email_otp(email, purpose=purpose)
        if not res.get("success"):
            return Response(
                {"error": res.get("error", "Failed to resend code."), "code": res.get("code", "COOLDOWN_ACTIVE"), "retry_after": res.get("retry_after")},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        resp_payload = {"message": "Verification code resent successfully."}
        if res.get("dev_otp"):
            resp_payload["dev_otp"] = res["dev_otp"]

        return Response(resp_payload, status=status.HTTP_200_OK)


class LoginView(APIView):
    """
    User Login:
    Rejects unverified accounts with HTTP 403 Forbidden.
    Preserves exact JWT response contract for desktop agent and frontend compatibility.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response(
                {"error": "Email and password are required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects(email=email).first()
        if not user or not user.check_password(password):
            return Response(
                {"error": "Invalid email or password.", "code": "INVALID_CREDENTIALS"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Enforce email verification (desktop agent and web)
        if not getattr(user, 'is_email_verified', False):
            # Dispatch fresh verification OTP so user can verify immediately
            try:
                otp_res = otp_client.send_email_otp(email, purpose="registration")
            except Exception:
                pass

            return Response({
                "error": "Your email address is not verified. A verification code has been dispatched to your email.",
                "code": "EMAIL_NOT_VERIFIED",
                "email": user.email,
                "requires_verification": True
            }, status=status.HTTP_403_FORBIDDEN)

        tokens = get_tokens_for_user(user)

        return Response({
            "access": tokens['access'],
            "refresh": tokens['refresh'],
            "user": user.to_dict()
        }, status=status.HTTP_200_OK)


class RefreshTokenView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_str = request.data.get('refresh')
        if not refresh_str:
            return Response(
                {"error": "Refresh token is required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            refresh = RefreshToken(refresh_str)
            user_id = refresh.payload.get('user_id')
            user = User.objects.get(id=user_id)
            new_tokens = get_tokens_for_user(user)
            return Response({
                "access": new_tokens['access'],
                "refresh": new_tokens['refresh']
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": f"Invalid or expired refresh token: {str(e)}", "code": "UNAUTHORIZED"},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


class UserMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(request.user.to_dict(), status=status.HTTP_200_OK)


class ProfileView(APIView):
    """
    Profile management:
    - GET: Retrieve current user profile
    - PUT/PATCH: Update personal profile details (full name, avatar, dob, gender, address, etc.)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(request.user.to_dict(), status=status.HTTP_200_OK)

    def put(self, request):
        return self._update(request)

    def patch(self, request):
        return self._update(request)

    def _update(self, request):
        user = request.user
        data = request.data

        # Updatable scalar string fields
        string_fields = ['full_name', 'avatar_url', 'gender', 'address']
        for field in string_fields:
            if field in data:
                val = str(data[field]).strip()
                setattr(user, field, val)

        # Cascading Location validation: country -> state -> city
        if 'country' in data or 'state' in data or 'city' in data:
            c_val = str(data.get('country', getattr(user, 'country', ''))).strip()
            s_val = str(data.get('state', getattr(user, 'state', ''))).strip()
            city_val = str(data.get('city', getattr(user, 'city', ''))).strip()

            # If user explicitly cleared country, reset dependent state and city
            if 'country' in data and not str(data['country']).strip():
                c_val = ''
                s_val = ''
                city_val = ''
            elif 'state' in data and not str(data['state']).strip():
                s_val = ''
                city_val = ''

            valid_loc, loc_err = validate_location(c_val, s_val, city_val)
            if not valid_loc:
                return Response(
                    {"error": loc_err, "code": "VALIDATION_ERROR"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.country = c_val
            user.state = s_val
            user.city = city_val

        # DOB: validate format and not a future date
        if 'dob' in data:
            dob_val = str(data['dob']).strip()
            if dob_val:
                try:
                    dob_date = datetime.strptime(dob_val, '%Y-%m-%d').date()
                    if dob_date >= dj_timezone.now().date():
                        return Response(
                            {"error": "Date of birth cannot be today or a future date.", "code": "VALIDATION_ERROR"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    user.dob = dob_val
                except ValueError:
                    return Response(
                        {"error": "Date of birth must be in YYYY-MM-DD format.", "code": "VALIDATION_ERROR"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                user.dob = ''

        # Mobile number: validate with phonenumbers (IN, US, GB, CA), normalize to E.164
        if 'mobile_number' in data:
            raw_mobile = str(data['mobile_number']).strip().replace(' ', '').replace('-', '')
            if raw_mobile:
                if re.search(r'[A-Za-z]', raw_mobile):
                    return Response(
                        {"error": "Mobile number must not contain letters or alphabetical characters.", "code": "VALIDATION_ERROR"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                try:
                    parsed = phonenumbers.parse(raw_mobile, None)
                    if not phonenumbers.is_valid_number(parsed):
                        return Response(
                            {"error": "Invalid mobile number format.", "code": "VALIDATION_ERROR"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    if parsed.country_code not in [91, 1, 44]:
                        return Response(
                            {"error": "Mobile number must be from India (+91), United States (+1), United Kingdom (+44), or Canada (+1).", "code": "VALIDATION_ERROR"},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    if parsed.country_code == 91:
                        nat_str = str(parsed.national_number)
                        if len(nat_str) != 10 or nat_str[0] not in '6789':
                            return Response(
                                {"error": "Indian mobile numbers must be exactly 10 digits starting with 6, 7, 8, or 9.", "code": "VALIDATION_ERROR"},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    normalized_mobile = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                except Exception as e:
                    return Response(
                        {"error": f"Invalid mobile number: {str(e)}", "code": "VALIDATION_ERROR"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                normalized_mobile = ''

            # If number changed, reset verification status; otherwise preserve
            if normalized_mobile != getattr(user, 'mobile_number', ''):
                user.mobile_number = normalized_mobile
                user.is_mobile_verified = False

        user.updated_at = datetime.utcnow()
        user.save()

        return Response({
            "message": "Profile updated successfully.",
            "user": user.to_dict()
        }, status=status.HTTP_200_OK)


class SendMobileOTPView(APIView):
    """
    Dispatches SMS OTP via Twilio through the mail_otp_server microservice.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        phone = request.data.get('phone', getattr(user, 'mobile_number', '')).strip().replace(' ', '').replace('-', '')

        if not phone:
            return Response(
                {"error": "Phone number is required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if re.search(r'[A-Za-z]', phone):
            return Response(
                {"error": "Mobile number must not contain letters or alphabetical characters.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            parsed = phonenumbers.parse(phone, None)
            if not phonenumbers.is_valid_number(parsed) or parsed.country_code not in [91, 1, 44]:
                return Response(
                    {"error": "Please enter a valid phone number from a supported country (+91, +1, +44).", "code": "VALIDATION_ERROR"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if parsed.country_code == 91:
                nat_str = str(parsed.national_number)
                if len(nat_str) != 10 or nat_str[0] not in '6789':
                    return Response(
                        {"error": "Indian mobile numbers must be exactly 10 digits starting with 6, 7, 8, or 9.", "code": "VALIDATION_ERROR"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            normalized_phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception as e:
            return Response(
                {"error": f"Invalid phone number: {str(e)}", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update user's mobile number if changed
        if normalized_phone != getattr(user, 'mobile_number', ''):
            user.mobile_number = normalized_phone
            user.is_mobile_verified = False
            user.save()

        res = otp_client.send_sms_otp(normalized_phone, purpose="mobile_verification")
        if not res.get("success"):
            return Response(
                {"error": res.get("error", "Failed to dispatch SMS OTP."), "code": res.get("code", "SMS_ERROR")},
                status=status.HTTP_400_BAD_REQUEST
            )

        resp_payload = {"message": "Verification code dispatched via SMS."}
        if res.get("dev_otp"):
            resp_payload["dev_otp"] = res["dev_otp"]

        return Response(resp_payload, status=status.HTTP_200_OK)


class VerifyMobileOTPView(APIView):
    """
    Verifies SMS OTP and marks mobile_number verified.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        otp = request.data.get('otp', '').strip()

        if not otp:
            return Response(
                {"error": "Verification OTP is required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.mobile_number:
            return Response(
                {"error": "No mobile number associated with your account.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        verify_res = otp_client.verify_sms_otp(user.mobile_number, otp, purpose="mobile_verification")
        if not verify_res.get("valid"):
            msg = verify_res.get("message", "Invalid or expired SMS verification code.")
            return Response(
                {"error": msg, "code": "INVALID_OTP", "remaining_attempts": verify_res.get("remaining_attempts")},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.is_mobile_verified = True
        user.updated_at = datetime.utcnow()
        user.save()

        return Response({
            "message": "Mobile number verified successfully.",
            "user": user.to_dict()
        }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    Allows authenticated users to change their password by validating current password.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')

        if not current_password or not new_password:
            return Response(
                {"error": "Current password and new password are required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(current_password):
            return Response(
                {"error": "Current password is incorrect.", "code": "INVALID_CREDENTIALS"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 8:
            return Response(
                {"error": "New password must be at least 8 characters long.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        user.save()

        return Response({
            "message": "Password changed successfully."
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """
    Requests password reset OTP.
    Dispatches 6-digit OTP via mail_otp_server (and generates a legacy token for compatibility).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response(
                {"error": "Email address is required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects(email=email).first()
        dev_token = None

        if user:
            # 1. Invalidate any existing unused tokens
            PasswordResetToken.objects(user=user, used=False).update(set__used=True)

            # 2. Dispatch OTP via mail_otp_server
            try:
                otp_res = otp_client.send_email_otp(email, purpose="password_reset")
                if otp_res.get("dev_otp"):
                    dev_token = otp_res["dev_otp"]
            except Exception as e:
                logger.warning(f"Could not dispatch OTP for password reset: {e}")

            # 3. Also store legacy token
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
            PasswordResetToken(
                user=user,
                token_hash=token_hash,
                expires_at=datetime.utcnow() + timedelta(minutes=15)
            ).save()
            if not dev_token:
                dev_token = raw_token

        resp_data = {
            "detail": "If an account with this email exists, password reset instructions have been dispatched.",
            "email": email
        }
        # Security: Never expose dev_token or OTP in production or development API responses.
        # Only attach during isolated automated test suite runs when TESTING is True:
        if getattr(settings, 'TESTING', False) and dev_token:
            resp_data["dev_token"] = dev_token

        return Response(resp_data, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    Confirms password reset using either 6-digit OTP or legacy token.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        token = request.data.get('token', '').strip()
        email = request.data.get('email', '').strip().lower()
        new_password = request.data.get('new_password', '')

        if not token or not new_password:
            return Response(
                {"error": "Token/OTP and new_password are required.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 8:
            return Response(
                {"error": "Password must be at least 8 characters long.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if email and new_password.lower() == email.lower():
            return Response(
                {"error": "Password cannot be the same as your email address.", "code": "VALIDATION_ERROR"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── OTP path: 6-digit numeric code + email ───────────────────────────────
        # Email is now always sent by the frontend; this is the primary reset path.
        if len(token) == 6 and token.isdigit():
            if not email:
                return Response(
                    {"error": "Email address is required when using a verification code.", "code": "VALIDATION_ERROR"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            verify_res = otp_client.verify_email_otp(email, token, purpose="password_reset")
            if not verify_res.get("valid"):
                return Response(
                    {"error": "Invalid or expired verification code.", "code": "INVALID_TOKEN"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user = User.objects(email=email).first()
            if not user:
                return Response(
                    {"error": "User not found.", "code": "NOT_FOUND"},
                    status=status.HTTP_404_NOT_FOUND
                )
            user.set_password(new_password)
            user.updated_at = datetime.utcnow()
            user.save()
            # Invalidate any pending legacy tokens for this user
            PasswordResetToken.objects(user=user, used=False).update(set__used=True)
            return Response(
                {"detail": "Password has been successfully reset. You may now log in with your new password."},
                status=status.HTTP_200_OK
            )

        # ── Legacy token hash path ────────────────────────────────────────────────
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        reset_doc = PasswordResetToken.objects(token_hash=token_hash, used=False).first()

        if not reset_doc:
            return Response(
                {"error": "Invalid or expired password reset token.", "code": "INVALID_TOKEN"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if reset_doc.expires_at < datetime.utcnow():
            reset_doc.used = True
            reset_doc.save()
            return Response(
                {"error": "Password reset token has expired. Please request a new one.", "code": "EXPIRED_TOKEN"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = reset_doc.user
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        user.save()

        reset_doc.used = True
        reset_doc.save()
        PasswordResetToken.objects(user=user, used=False).update(set__used=True)

        return Response(
            {"detail": "Password has been successfully reset. You may now log in with your new password."},
            status=status.HTTP_200_OK
        )
