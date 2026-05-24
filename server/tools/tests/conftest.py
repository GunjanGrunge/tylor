"""
Shared pytest fixtures and environment setup for server/tools/tests.
"""
import os
import pytest


# ── Disable Bumblebee security gate in all tests ──────────────────────────────
# Bumblebee CLI is not installed in CI / local dev environments.
# Setting this env var prevents validate_skill_package() from raising
# a ToolError when the binary is missing.
def pytest_configure(config):
    os.environ.setdefault("BUMBLEBEE_ENABLED", "false")
