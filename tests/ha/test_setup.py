from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mojelektro_stats.const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_USAGE_POINTS,
    DOMAIN,
    SERVER_TEST,
)


@pytest.mark.ha
async def test_setup_and_unload(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={
            CONF_TOKEN: "tok",
            CONF_SERVER: SERVER_TEST,
            CONF_USAGE_POINTS: [],
        },
        title="Moj Elektro",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
