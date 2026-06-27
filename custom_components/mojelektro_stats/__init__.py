from __future__ import annotations

from contextlib import AsyncExitStack
from functools import partial
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from custom_components.mojelektro_stats import _bootstrap  # noqa: F401
from custom_components.mojelektro_stats.const import (
    CONF_INFLUXDB,
    CONF_INFLUXDB_BUCKET,
    CONF_INFLUXDB_ORG,
    CONF_INFLUXDB_TOKEN,
    CONF_INFLUXDB_URL,
    CONF_ROUTING,
    CONF_SERVER,
    CONF_TOKEN,
    CONF_USAGE_POINTS,
    DATA_CONFIG_VERSION,
    DOMAIN,
    PLATFORMS,
    SERVER_TEST,
    SINK_INFLUXDB,
    SINK_STATISTICS,
)
from custom_components.mojelektro_stats.coordinator import MojElektroDataUpdateCoordinator
from custom_components.mojelektro_stats.dispatcher import Dispatcher
from custom_components.mojelektro_stats.sinks import InfluxDBSink, Sink, StatisticsSink
from mojelektro_api import MojElektroClient, Server


def _server_from_str(value: str) -> Server:
    return Server.TEST if value == SERVER_TEST else Server.PRODUCTION


def _make_client(token: str, server: Server) -> MojElektroClient:
    """Factory hook so tests can patch this without monkey-patching the lib."""
    return MojElektroClient(token, server=server)


_V1_TO_V2_ROUTING: dict[str, list[str]] = {
    "skip": [],
    "sensor": [],
    "sensor+backfill": [SINK_STATISTICS],
    "influxdb": [SINK_INFLUXDB],
}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2: routing values become lists of sink names instead of strings.

    v1 had four mutually-exclusive choices per reading type (skip / sensor /
    sensor+backfill / influxdb). v2 lets the user enable Statistics and InfluxDB
    independently per reading type. We collapse "sensor" -> [] (the entity
    platform was removed) and "sensor+backfill" -> ["statistics"].
    """
    if entry.version >= DATA_CONFIG_VERSION:
        return True
    data = dict(entry.data)
    if entry.version < 2:
        usage_points = [dict(up) for up in data.get(CONF_USAGE_POINTS, [])]
        for up in usage_points:
            routing = up.get(CONF_ROUTING, {})
            up[CONF_ROUTING] = {
                name: (
                    list(value)
                    if isinstance(value, list)
                    else _V1_TO_V2_ROUTING.get(str(value), [])
                )
                for name, value in routing.items()
            }
        data[CONF_USAGE_POINTS] = usage_points
    hass.config_entries.async_update_entry(entry, data=data, version=DATA_CONFIG_VERSION)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    server = _server_from_str(entry.data[CONF_SERVER])
    stack = AsyncExitStack()
    await stack.__aenter__()
    client = await hass.async_add_executor_job(
        partial(_make_client, entry.data[CONF_TOKEN], server)
    )
    await stack.enter_async_context(client)

    sinks: dict[str, Sink] = {SINK_STATISTICS: StatisticsSink(hass)}

    influx_cfg: dict[str, Any] | None = entry.data.get(CONF_INFLUXDB)
    if influx_cfg:
        # Build the InfluxDB httpx client off-loop too — same SSL-load reason.
        influx_http = await hass.async_add_executor_job(httpx.AsyncClient)
        await stack.enter_async_context(influx_http)
        sinks[SINK_INFLUXDB] = InfluxDBSink(
            influx_http,
            url=influx_cfg[CONF_INFLUXDB_URL],
            org=influx_cfg[CONF_INFLUXDB_ORG],
            bucket=influx_cfg[CONF_INFLUXDB_BUCKET],
            token=influx_cfg[CONF_INFLUXDB_TOKEN],
        )

    coordinator = MojElektroDataUpdateCoordinator(
        hass,
        client=client,
        usage_points=entry.data.get(CONF_USAGE_POINTS, []),
        dispatcher=Dispatcher(sinks),
    )
    coordinator.config_entry = entry
    coordinator.runtime_stack = stack

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()

    # Daily sync at 06:00 local time. The API publishes prior-day data, so a
    # morning run picks up a complete previous day. async_track_time_change
    # uses HA's configured timezone and handles DST.
    entry.async_on_unload(
        async_track_time_change(
            hass,
            lambda now: hass.async_create_task(coordinator.async_refresh()),
            hour=6,
            minute=0,
            second=0,
        )
    )

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if PLATFORMS:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    else:
        unloaded = True
    if unloaded:
        coordinator: MojElektroDataUpdateCoordinator | None = hass.data.get(DOMAIN, {}).pop(
            entry.entry_id, None
        )
        if coordinator is not None:
            stack: AsyncExitStack = coordinator.runtime_stack
            await stack.aclose()
    return unloaded
