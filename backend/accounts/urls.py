from django.urls import path
from accounts.views import (
    RegisterView,
    VerifyEmailOTPView,
    ResendOTPView,
    LoginView,
    RefreshTokenView,
    LogoutView,
    UserMeView,
    ProfileView,
    SendMobileOTPView,
    VerifyMobileOTPView,
    ChangePasswordView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('verify-email-otp/', VerifyEmailOTPView.as_view(), name='auth-verify-email-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='auth-resend-otp'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', RefreshTokenView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', UserMeView.as_view(), name='auth-me'),
    path('profile/', ProfileView.as_view(), name='auth-profile'),
    path('mobile/send-otp/', SendMobileOTPView.as_view(), name='auth-mobile-send-otp'),
    path('mobile/verify-otp/', VerifyMobileOTPView.as_view(), name='auth-mobile-verify-otp'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
]
