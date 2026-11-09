import mongoengine as me
from datetime import datetime
from django.contrib.auth.hashers import make_password, check_password
from cloud_storage.timezone_utils import to_iso_utc

class User(me.Document):
    email = me.StringField(required=True, unique=True)
    password = me.StringField(required=True)  # Argon2 hashed password
    is_email_verified = me.BooleanField(default=False)
    
    # Profile Information
    full_name = me.StringField(max_length=100, default="")
    avatar_url = me.StringField(default="")
    mobile_number = me.StringField(max_length=20, default="")
    is_mobile_verified = me.BooleanField(default=False)
    dob = me.StringField(max_length=20, default="")  # YYYY-MM-DD
    gender = me.StringField(max_length=20, default="")
    country = me.StringField(max_length=100, default="")
    state = me.StringField(max_length=100, default="")
    city = me.StringField(max_length=100, default="")
    address = me.StringField(max_length=255, default="")

    # Storage Metadata
    storage_quota_bytes = me.IntField(default=5 * 1024 * 1024 * 1024)  # 5 GB default
    storage_used_bytes = me.IntField(default=0)
    created_at = me.DateTimeField(default=datetime.utcnow)
    updated_at = me.DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'users',
        'indexes': ['email', 'mobile_number']
    }

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def pk(self):
        return str(self.id)

    def set_password(self, raw_password):
        # Uses PASSWORD_HASHERS setting (Argon2 by default)
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "is_email_verified": getattr(self, 'is_email_verified', False),
            "full_name": getattr(self, 'full_name', ""),
            "avatar_url": getattr(self, 'avatar_url', ""),
            "mobile_number": getattr(self, 'mobile_number', ""),
            "is_mobile_verified": getattr(self, 'is_mobile_verified', False),
            "dob": getattr(self, 'dob', ""),
            "gender": getattr(self, 'gender', ""),
            "country": getattr(self, 'country', ""),
            "state": getattr(self, 'state', ""),
            "city": getattr(self, 'city', ""),
            "address": getattr(self, 'address', ""),
            "storage_quota_bytes": self.storage_quota_bytes,
            "storage_used_bytes": self.storage_used_bytes,
            "created_at": to_iso_utc(self.created_at),
            "updated_at": to_iso_utc(self.updated_at) if hasattr(self, 'updated_at') else None,
        }

class PasswordResetToken(me.Document):
    user = me.ReferenceField(User, required=True)
    token_hash = me.StringField(required=True, unique=True)
    expires_at = me.DateTimeField(required=True)
    used = me.BooleanField(default=False)
    created_at = me.DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'password_reset_tokens',
        'indexes': ['token_hash', 'user', 'expires_at']
    }
