# Dev Dockerfile for Home Assistant with the Moj Elektro integration.
# The integration (including the vendored lib) is bind-mounted at runtime;
# restart HA after edits — no rebuild needed for integration changes.

FROM ghcr.io/home-assistant/home-assistant:stable
