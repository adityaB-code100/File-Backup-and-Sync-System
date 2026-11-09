import sys
import os
import pytest

# Ensure mail_otp_server directory is at the beginning of sys.path
server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# Remove any root app module
for mod in list(sys.modules.keys()):
    if mod == "app" or mod.startswith("app."):
        del sys.modules[mod]

from app.config import settings
settings.TESTING = True

from app.main import app
from app.services.otp_service import otp_service

class ResponseWrapper:
    def __init__(self, res):
        self._res = res

    @property
    def status_code(self):
        return self._res.status_code

    def json(self):
        return self._res.get_json()

    @property
    def text(self):
        return self._res.get_data(as_text=True)

    def __getattr__(self, name):
        return getattr(self._res, name)

class FlaskTestClientWrapper:
    def __init__(self, client):
        self._client = client

    def get(self, *args, **kwargs):
        res = self._client.get(*args, **kwargs)
        return ResponseWrapper(res)

    def post(self, *args, **kwargs):
        res = self._client.post(*args, **kwargs)
        return ResponseWrapper(res)

@pytest.fixture(autouse=True)
def clean_otp_store():
    """Wipes in-memory OTP store before each test."""
    otp_service.clear()
    settings.TESTING = True
    yield
    otp_service.clear()

@pytest.fixture
def client():
    return FlaskTestClientWrapper(app.test_client())

@pytest.fixture
def auth_headers():
    return {"X-Service-Secret": settings.OTP_SERVICE_SECRET}
