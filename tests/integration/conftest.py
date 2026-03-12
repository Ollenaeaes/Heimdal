"""Integration test configuration.

These tests require Docker Compose services to be running.
They are automatically skipped if the API server is unreachable.
"""

import os

import pytest

# Default to localhost; override with HEIMDAL_API_URL env var
API_BASE_URL = os.environ.get("HEIMDAL_API_URL", "http://localhost:8000")
WS_BASE_URL = os.environ.get("HEIMDAL_WS_URL", "ws://localhost:8000")


def _api_is_reachable() -> bool:
    """Check if the Heimdal API server is reachable."""
    try:
        import urllib.request
        urllib.request.urlopen(f"{API_BASE_URL}/api/health", timeout=3)
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _api_is_reachable(),
    reason="Heimdal API server not reachable (Docker Compose not running)",
)
