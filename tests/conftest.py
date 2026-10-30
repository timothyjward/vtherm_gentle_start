"""Fixtures of the vtherm_gentle_start tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the tests load the integration of this repository."""
    yield
