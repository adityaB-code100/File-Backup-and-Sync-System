import re
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")

class EmailSendOTPRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(default="registration", description="Purpose: registration, password_reset, email_change")

    @field_validator("purpose")
    def validate_purpose(cls, v: str) -> str:
        allowed = {"registration", "password_reset", "email_change"}
        if v not in allowed:
            raise ValueError(f"Invalid purpose '{v}'. Must be one of {allowed}")
        return v

class EmailVerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit numeric OTP")
    purpose: str = Field(default="registration")

    @field_validator("otp")
    def validate_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must consist only of digits.")
        return v

class SMSSendOTPRequest(BaseModel):
    phone: str = Field(..., description="Phone number in E.164 format (e.g., +1234567890)")
    purpose: str = Field(default="mobile_verification")

    @field_validator("phone")
    def validate_phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        if not E164_REGEX.match(v):
            raise ValueError("Phone number must be in E.164 format (e.g. +1234567890).")
        return v

class SMSVerifyOTPRequest(BaseModel):
    phone: str = Field(..., description="Phone number in E.164 format")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit numeric OTP")
    purpose: str = Field(default="mobile_verification")

    @field_validator("phone")
    def validate_phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        if not E164_REGEX.match(v):
            raise ValueError("Phone number must be in E.164 format (e.g. +1234567890).")
        return v

    @field_validator("otp")
    def validate_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must consist only of digits.")
        return v

class OTPResponse(BaseModel):
    success: bool
    message: str
    detail: Optional[str] = None
    retry_after: Optional[int] = None
    # For testing/dev environments only
    dev_otp: Optional[str] = None

class OTPVerifyResponse(BaseModel):
    valid: bool
    message: str
    remaining_attempts: Optional[int] = None

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    version: str

