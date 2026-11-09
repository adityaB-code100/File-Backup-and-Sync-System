import sys
import os

# Set working directory to mail_otp_server
server_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(server_dir)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# Remove any root app module
for mod in list(sys.modules.keys()):
    if mod == "app" or mod.startswith("app."):
        del sys.modules[mod]

import pytest

if __name__ == "__main__":
    # Disable interfering global plugins
    args = [
        "tests",
        "-v",
        "-p", "no:django",
        "-p", "no:dash",
        "-p", "no:langsmith",
    ]
    exit_code = pytest.main(args)
    sys.exit(exit_code)

