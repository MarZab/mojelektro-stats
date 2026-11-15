"""Let pytest-homeassistant-custom-component 0.13.375 (built for HA 2026.10.4)
load on Home Assistant 2026.11.

Loaded with ``-p ha_test_compat`` from pytest's addopts, which pytest imports
before any entry-point plugin. It fixes two things:

- HA 2026.11 aliases ``httpx`` to ``httpx2`` when ``homeassistant`` is first
  imported and refuses if ``httpx`` was imported before. The plugin imports
  ``respx`` (and so ``httpx``) ahead of HA, so import HA first.
- ``_clear_logger_overwrites`` moved from ``homeassistant.components.logger``
  to its ``helpers`` module; the plugin still imports the old location.

Delete this package (and the ``-p`` option, the dependency and the
``override-dependencies`` floor in the root pyproject.toml) once the plugin
publishes a release for the Home Assistant version in use.
"""

from __future__ import annotations

import homeassistant.components.logger as _logger  # first: sets up the httpx alias
from homeassistant.components.logger import helpers as _logger_helpers

if not hasattr(_logger, "_clear_logger_overwrites"):
    _logger._clear_logger_overwrites = _logger_helpers._clear_logger_overwrites  # type: ignore[attr-defined]
