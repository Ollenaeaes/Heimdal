"""Shared pytest configuration and fixtures."""

import os

# Ensure a DATABASE_URL is set for tests (won't actually connect in unit tests)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
