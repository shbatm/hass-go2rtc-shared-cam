"""Test bootstrap for pytest."""
# Load Home Assistant pytest plugin when available so fixtures like `hass`
# and `mock_config_entry` are provided.
pytest_plugins = ("homeassistant",)

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import homeassistant  # noqa: F401
except Exception:
    pass
