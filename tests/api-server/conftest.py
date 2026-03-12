"""Conftest for api-server tests.

Ensures the api-server service directory is on sys.path so that
``import main`` resolves to services/api-server/main.py rather than
any other service's main.py.
"""

import os
import sys

# Ensure DATABASE_URL is set for tests
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)

# Insert the api-server path at the front so `import main` finds the right module
_api_server_dir = os.path.join(
    os.path.dirname(__file__), "..", "..", "services", "api-server"
)
_api_server_dir = os.path.normpath(_api_server_dir)
if _api_server_dir not in sys.path:
    sys.path.insert(0, _api_server_dir)
