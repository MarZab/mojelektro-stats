"""Fixtures for Home Assistant integration tests.

`pytest-homeassistant-custom-component` supplies `hass`, `enable_custom_integrations`,
`recorder_mock`, `MockConfigEntry`, etc. Tests must request these explicitly because
`recorder_mock` has to run before `hass` (it asserts hass isn't set up yet) and
`enable_custom_integrations` requires `hass` (so it can't be autouse'd alongside
recorder-backed tests).
"""
