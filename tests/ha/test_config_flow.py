"""ConfigFlow + OptionsFlow tests.

Routing shape: each reading type stores a list of sink names (subset of
{"statistics", "influxdb"}). Empty list -> nothing dispatched.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mojelektro_stats.const import (
    CONF_BACKFILL_FROM,
    CONF_IDENTIFIKATOR,
    CONF_INFLUXDB,
    CONF_INFLUXDB_API_VERSION,
    CONF_INFLUXDB_BUCKET,
    CONF_INFLUXDB_DATABASE,
    CONF_INFLUXDB_ORG,
    CONF_INFLUXDB_PASSWORD,
    CONF_INFLUXDB_TOKEN,
    CONF_INFLUXDB_URL,
    CONF_INFLUXDB_USERNAME,
    CONF_NAZIV,
    CONF_ROUTING,
    CONF_SERVER,
    CONF_SYNC_ENABLED,
    CONF_SYNC_TIME,
    CONF_TOKEN,
    CONF_USAGE_POINTS,
    DOMAIN,
    INFLUXDB_V1,
    INFLUXDB_V2,
    SERVER_TEST,
    SINK_INFLUXDB,
    SINK_STATISTICS,
)
from mojelektro_api import KNOWN_READING_TYPES, AuthError, NotFoundError, TransportError

_VALIDATE = "custom_components.mojelektro_stats.config_flow._validate_meter"
_VALIDATE_INFLUX = "custom_components.mojelektro_stats.config_flow._validate_influxdb"
_FAKE_PAYLOAD: dict[str, Any] = {
    "naziv": "Some Place 12, Ljubljana",
    "identifikator": {
        "enotniIdentifikatorMerilnegaMesta": "4-1234567",
        "gsrn": "100000000000000000",
    },
}


def _all_empty() -> dict[str, list[str]]:
    return {rt.name: [] for rt in KNOWN_READING_TYPES}


@pytest.mark.ha
async def test_user_step_shows_form(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.ha
@pytest.mark.parametrize(
    ("exc", "expected_errors"),
    [
        (AuthError("nope"), {"base": "invalid_auth"}),
        (NotFoundError("missing"), {CONF_IDENTIFIKATOR: "unknown_meter"}),
        (TransportError("boom"), {"base": "cannot_connect"}),
    ],
)
async def test_add_usage_point_error_mapping(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
    exc: Exception,
    expected_errors: dict[str, str],
) -> None:
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_TOKEN: "tok", CONF_SERVER: SERVER_TEST}
    )
    with patch(_VALIDATE, side_effect=exc):
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_IDENTIFIKATOR: "GSRN1"}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == expected_errors


@pytest.mark.ha
async def test_full_flow_routing_is_list_of_sinks(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_TOKEN: "tok", CONF_SERVER: SERVER_TEST}
    )
    with patch(_VALIDATE, return_value=_FAKE_PAYLOAD):
        await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_IDENTIFIKATOR: "GSRN1"}
        )
        routing: dict[str, list[str]] = _all_empty()
        routing[KNOWN_READING_TYPES[0].name] = [SINK_STATISTICS]
        routing[KNOWN_READING_TYPES[1].name] = [SINK_STATISTICS, SINK_INFLUXDB]
        with patch(_VALIDATE_INFLUX, return_value=123):
            await hass.config_entries.flow.async_configure(first["flow_id"], routing)
            await hass.config_entries.flow.async_configure(
                first["flow_id"], {CONF_INFLUXDB_API_VERSION: INFLUXDB_V2}
            )
            result = await hass.config_entries.flow.async_configure(
                first["flow_id"],
                {
                    CONF_INFLUXDB_URL: "http://influx:8086",
                    CONF_INFLUXDB_ORG: "home",
                    CONF_INFLUXDB_BUCKET: "elektro",
                    CONF_INFLUXDB_TOKEN: "x",
                },
            )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["description"] == "influxdb_verified"
    assert result["description_placeholders"] == {"count": "123"}
    # The created entry's title (what HA shows in Devices & Services) defaults
    # to the meter's naziv, not the integration's generic name.
    assert result["title"] == "Some Place 12, Ljubljana"
    point = result["data"][CONF_USAGE_POINTS][0]
    assert point[CONF_NAZIV] == "Some Place 12, Ljubljana"
    assert point[CONF_ROUTING][KNOWN_READING_TYPES[0].name] == [SINK_STATISTICS]
    assert point[CONF_ROUTING][KNOWN_READING_TYPES[1].name] == [
        SINK_STATISTICS,
        SINK_INFLUXDB,
    ]


@pytest.mark.ha
async def test_influxdb_v1_form_composes_v2_shape(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    """Picking v1 collects native fields and stores them in the v2 shape."""
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_TOKEN: "tok", CONF_SERVER: SERVER_TEST}
    )
    with patch(_VALIDATE, return_value=_FAKE_PAYLOAD):
        await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_IDENTIFIKATOR: "GSRN1"}
        )
        routing: dict[str, list[str]] = _all_empty()
        routing[KNOWN_READING_TYPES[0].name] = [SINK_INFLUXDB]
        await hass.config_entries.flow.async_configure(first["flow_id"], routing)
        await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_INFLUXDB_API_VERSION: INFLUXDB_V1}
        )
        with patch(_VALIDATE_INFLUX, return_value=5) as validate:
            result = await hass.config_entries.flow.async_configure(
                first["flow_id"],
                {
                    CONF_INFLUXDB_URL: "http://a0d7b954-influxdb:8086",
                    CONF_INFLUXDB_DATABASE: "homeassistant",
                    CONF_INFLUXDB_USERNAME: "homeassistant",
                    CONF_INFLUXDB_PASSWORD: "secret",
                },
            )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    stored = result["data"][CONF_INFLUXDB]
    assert stored[CONF_INFLUXDB_API_VERSION] == INFLUXDB_V1
    assert stored[CONF_INFLUXDB_BUCKET] == "homeassistant/autogen"
    assert stored[CONF_INFLUXDB_TOKEN] == "homeassistant:secret"
    assert stored[CONF_INFLUXDB_ORG] == "-"
    # The probe receives the composed v2 shape, not the raw v1 fields.
    composed = validate.call_args.args[1]
    assert composed[CONF_INFLUXDB_TOKEN] == "homeassistant:secret"


@pytest.mark.ha
async def test_options_flow_backfill_triggers_coordinator(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            CONF_TOKEN: "tok",
            CONF_SERVER: SERVER_TEST,
            CONF_USAGE_POINTS: [
                {
                    CONF_IDENTIFIKATOR: "GSRN1",
                    CONF_NAZIV: "X",
                    CONF_ROUTING: {KNOWN_READING_TYPES[0].name: [SINK_STATISTICS]},
                }
            ],
        },
    )
    entry.add_to_hass(hass)
    # Wire a stub coordinator into hass.data so the OptionsFlow can find it.
    backfill = AsyncMock(return_value=3)
    stub = type("StubCoord", (), {"async_backfill_from": backfill})()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = stub

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "backfill"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_BACKFILL_FROM: "2026-05-01"}
    )
    # Backfill is scheduled as a background task; wait for it.
    await hass.async_block_till_done()
    backfill.assert_awaited_once()


@pytest.mark.ha
async def test_influxdb_config_rejects_bad_connection(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    from custom_components.mojelektro_stats.sinks.influxdb import InfluxDBAuthError

    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_TOKEN: "tok", CONF_SERVER: SERVER_TEST}
    )
    with patch(_VALIDATE, return_value=_FAKE_PAYLOAD):
        await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_IDENTIFIKATOR: "GSRN1"}
        )
        routing: dict[str, list[str]] = _all_empty()
        routing[KNOWN_READING_TYPES[0].name] = [SINK_INFLUXDB]
        await hass.config_entries.flow.async_configure(first["flow_id"], routing)
        await hass.config_entries.flow.async_configure(
            first["flow_id"], {CONF_INFLUXDB_API_VERSION: INFLUXDB_V2}
        )
        with patch(_VALIDATE_INFLUX, side_effect=InfluxDBAuthError("nope")):
            result = await hass.config_entries.flow.async_configure(
                first["flow_id"],
                {
                    CONF_INFLUXDB_URL: "http://influx:8086",
                    CONF_INFLUXDB_ORG: "home",
                    CONF_INFLUXDB_BUCKET: "elektro",
                    CONF_INFLUXDB_TOKEN: "bad",
                },
            )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "influxdb_config"
    assert result["errors"] == {"base": "invalid_influx_auth"}


@pytest.mark.ha
async def test_options_influxdb_config_reports_point_count(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            CONF_TOKEN: "tok",
            CONF_SERVER: SERVER_TEST,
            CONF_USAGE_POINTS: [
                {
                    CONF_IDENTIFIKATOR: "GSRN1",
                    CONF_NAZIV: "X",
                    CONF_ROUTING: {KNOWN_READING_TYPES[0].name: [SINK_INFLUXDB]},
                }
            ],
            CONF_INFLUXDB: {
                CONF_INFLUXDB_URL: "http://influx:8086",
                CONF_INFLUXDB_ORG: "home",
                CONF_INFLUXDB_BUCKET: "elektro",
                CONF_INFLUXDB_TOKEN: "old",
            },
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "influxdb_version"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_INFLUXDB_API_VERSION: INFLUXDB_V2}
    )
    with patch(_VALIDATE_INFLUX, return_value=7):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_INFLUXDB_URL: "http://influx:8086",
                CONF_INFLUXDB_ORG: "home",
                CONF_INFLUXDB_BUCKET: "elektro",
                CONF_INFLUXDB_TOKEN: "new",
            },
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["description"] == "influxdb_verified"
    assert result["description_placeholders"] == {"count": "7"}
    assert entry.data[CONF_INFLUXDB][CONF_INFLUXDB_TOKEN] == "new"


@pytest.mark.ha
async def test_options_sync_schedule_persists_toggle_and_time(
    recorder_mock: object,
    enable_custom_integrations: object,
    hass: HomeAssistant,
) -> None:
    """The dedicated sync-schedule menu step writes the toggle + time to the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={
            CONF_TOKEN: "tok",
            CONF_SERVER: SERVER_TEST,
            CONF_USAGE_POINTS: [
                {
                    CONF_IDENTIFIKATOR: "GSRN1",
                    CONF_NAZIV: "X",
                    CONF_ROUTING: {KNOWN_READING_TYPES[0].name: [SINK_STATISTICS]},
                }
            ],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sync_schedule"}
    )
    assert result["step_id"] == "sync_schedule"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SYNC_ENABLED: False, CONF_SYNC_TIME: "09:30:00"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_SYNC_ENABLED] is False
    assert entry.data[CONF_SYNC_TIME] == "09:30:00"
