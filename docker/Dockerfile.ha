# Dev Dockerfile for Home Assistant with the Moj Elektro integration.
# The integration (including the vendored lib) is bind-mounted at runtime;
# restart HA after edits — no rebuild needed for integration changes.

# Pinned to the Home Assistant the tests run against (override-dependencies
# in pyproject.toml); bump both together.
FROM ghcr.io/home-assistant/home-assistant:2026.11.1
