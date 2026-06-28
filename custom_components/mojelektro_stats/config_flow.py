"""ConfigFlow + OptionsFlow for the Moj Elektro integration.

One config entry pairs one Moj Elektro token (a single "Storitev" / service
account) with exactly one merilno mesto. The API permits more than one meter
per service, but in practice each user controls one and the multi-meter UX
was more confusion than value. To track several meters, add multiple entries.

ConfigFlow:
1. `user` — token + server.
2. `add_usage_point` — identifikator; validates via `get_merilno_mesto`
   and captures `naziv`.
3. `configure_measurements` — one BooleanSelector per (reading_type, sink)
   pair so the label and toggle sit on the same row. Routing is persisted
   as `{rt_name: [sink, ...]}` lists.
4. `influxdb_config` — only if at least one reading type opts into InfluxDB.

OptionsFlow:
- Menu: edit the usage point's measurement routing, adjust the daily sync
  schedule (on/off + time), kick off a backfill, reconfigure InfluxDB
  (when applicable), save.
- Backfill runs `coordinator.async_backfill_from(date)` in a background task
  so the form returns immediately; results show up in the logs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Final, cast

import httpx
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    DateSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from custom_components.mojelektro_stats import _bootstrap  # noqa: F401
from custom_components.mojelektro_stats.const import (
    CONF_BACKFILL_FROM,
    CONF_IDENTIFIKATOR,
    CONF_INFLUXDB,
    CONF_INFLUXDB_API_VERSION,
    CONF_INFLUXDB_BUCKET,
    CONF_INFLUXDB_DATABASE,
    CONF_INFLUXDB_ORG,
    CONF_INFLUXDB_PASSWORD,
    CONF_INFLUXDB_RETENTION,
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
    DEFAULT_INFLUXDB_RETENTION,
    DEFAULT_SYNC_ENABLED,
    DEFAULT_SYNC_TIME,
    DOMAIN,
    INFLUXDB_V1,
    INFLUXDB_V2,
    SERVER_PROD,
    SERVER_TEST,
    SINK_INFLUXDB,
    SINK_OPTIONS,
)
from custom_components.mojelektro_stats.sinks.influxdb import (
    InfluxDBAuthError,
    InfluxDBConnectionError,
    InfluxDBDatabaseNotFound,
    InfluxDBError,
    probe_influxdb_connection,
)
from mojelektro_api import (
    KNOWN_READING_TYPES,
    AuthError,
    InvalidRequestError,
    MerilnoMesto,
    MojElektroClient,
    MojElektroError,
    NotFoundError,
    Server,
    TransportError,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


# Multi-select per reading type: 0, 1, or both of "Statistics" / "InfluxDB".
# LIST mode renders the two options as checkbox-toggles below the row's label.
_SINK_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        mode=SelectSelectorMode.LIST,
        multiple=True,
        translation_key="sink",
        options=[SelectOptionDict(value=v, label=v) for v in SINK_OPTIONS],
    )
)
_DATE_SELECTOR = DateSelector()
_TIME_SELECTOR = TimeSelector()
_BOOL_SELECTOR = BooleanSelector()
_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

# Radio toggle on the first InfluxDB step. v2 is the default (cloud / OSS 2.x);
# v1 targets the Home Assistant InfluxDB 1.8 add-on via its v2-compat API.
# Labels are set explicitly (no translation_key) so the radios always render
# readable text even if HA's translation cache is stale — and InfluxDB version
# names aren't worth translating anyway.
_INFLUXDB_VERSION_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        mode=SelectSelectorMode.LIST,
        options=[
            SelectOptionDict(value=INFLUXDB_V2, label="InfluxDB 2.x / Cloud"),
            SelectOptionDict(
                value=INFLUXDB_V1, label="InfluxDB 1.x (Home Assistant add-on)"
            ),
        ],
    )
)

# Defaults for the v1 form, matching a stock Home Assistant InfluxDB add-on.
_V1_DEFAULT_URL: Final = "http://a0d7b954-influxdb:8086"
_V1_DEFAULT_DATABASE: Final = "homeassistant"
_V1_DEFAULT_USERNAME: Final = "homeassistant"


# Environment-variable overrides for the InfluxDB defaults. Set on the HA
# container to skip re-typing connection details in dev (see docker/compose.yaml).
_ENV_INFLUXDB: Final = {
    CONF_INFLUXDB_URL: "MOJELEKTRO_INFLUXDB_URL",
    CONF_INFLUXDB_ORG: "MOJELEKTRO_INFLUXDB_ORG",
    CONF_INFLUXDB_BUCKET: "MOJELEKTRO_INFLUXDB_BUCKET",
    CONF_INFLUXDB_TOKEN: "MOJELEKTRO_INFLUXDB_TOKEN",
}


def _server_from_str(value: str) -> Server:
    return Server.TEST if value == SERVER_TEST else Server.PRODUCTION


def _compose_v1(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Fold native v1 form fields into the v2 shape the sink consumes.

    token -> "username:password", bucket -> "database/retention_policy".
    org is a placeholder ("-") since InfluxDB 1.x ignores it.
    """
    database = str(user_input[CONF_INFLUXDB_DATABASE]).strip()
    retention = str(user_input.get(CONF_INFLUXDB_RETENTION) or DEFAULT_INFLUXDB_RETENTION).strip()
    username = str(user_input.get(CONF_INFLUXDB_USERNAME) or "")
    password = str(user_input.get(CONF_INFLUXDB_PASSWORD) or "")
    bucket = f"{database}/{retention}" if retention else database
    return {
        CONF_INFLUXDB_API_VERSION: INFLUXDB_V1,
        CONF_INFLUXDB_URL: str(user_input[CONF_INFLUXDB_URL]),
        CONF_INFLUXDB_ORG: "-",
        CONF_INFLUXDB_BUCKET: bucket,
        CONF_INFLUXDB_TOKEN: f"{username}:{password}",
    }


def _decompose_v1(existing: Mapping[str, Any]) -> dict[str, str]:
    """Split a stored v2-shaped v1 config back into native fields for pre-fill."""
    database, _, retention = str(existing.get(CONF_INFLUXDB_BUCKET, "")).partition("/")
    username, _, password = str(existing.get(CONF_INFLUXDB_TOKEN, "")).partition(":")
    return {
        CONF_INFLUXDB_URL: str(existing.get(CONF_INFLUXDB_URL, "")),
        CONF_INFLUXDB_DATABASE: database,
        CONF_INFLUXDB_RETENTION: retention,
        CONF_INFLUXDB_USERNAME: username,
        CONF_INFLUXDB_PASSWORD: password,
    }


async def _validate_meter(
    hass: HomeAssistant, token: str, server: Server, identifikator: str
) -> MerilnoMesto:
    """Probe the API with the user's token + identifikator and return the payload."""
    client = await hass.async_add_executor_job(partial(MojElektroClient, token, server=server))
    async with client:
        return await client.get_merilno_mesto(identifikator)


def _extract_naziv(payload: MerilnoMesto) -> str:
    return str(payload.get("naziv") or "")


def _routing_uses_influxdb(usage_points: list[Mapping[str, Any]]) -> bool:
    return any(
        SINK_INFLUXDB in sinks for up in usage_points for sinks in up.get(CONF_ROUTING, {}).values()
    )


def _routing_schema(existing: Mapping[str, list[str]] | None = None) -> vol.Schema:
    existing = existing or {}
    return vol.Schema(
        {
            vol.Required(rt.name, default=existing.get(rt.name, [])): _SINK_SELECTOR
            for rt in KNOWN_READING_TYPES
        }
    )


class _FlowStepsMixin:
    _data: dict[str, Any]
    _pending_point: dict[str, Any]
    _editing_index: int | None
    _influxdb_point_count: int | None

    if TYPE_CHECKING:
        hass: HomeAssistant

        def async_show_form(self, **kwargs: Any) -> ConfigFlowResult: ...
        def async_create_entry(self, **kwargs: Any) -> ConfigFlowResult: ...

    async def _after_configure_point(self) -> ConfigFlowResult:
        raise NotImplementedError

    async def async_step_add_usage_point(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            server = _server_from_str(self._data[CONF_SERVER])
            try:
                payload = await _validate_meter(
                    self.hass,
                    self._data[CONF_TOKEN],
                    server,
                    user_input[CONF_IDENTIFIKATOR],
                )
            except AuthError:
                errors["base"] = "invalid_auth"
            except NotFoundError:
                errors[CONF_IDENTIFIKATOR] = "unknown_meter"
            except TransportError:
                errors["base"] = "cannot_connect"
            except InvalidRequestError:
                errors["base"] = "invalid_input"
            except MojElektroError:
                errors["base"] = "unknown"
            else:
                self._editing_index = None
                self._pending_point = {
                    CONF_IDENTIFIKATOR: user_input[CONF_IDENTIFIKATOR],
                    CONF_NAZIV: _extract_naziv(payload),
                    CONF_ROUTING: {},
                }
                return await self.async_step_configure_measurements()
        return self.async_show_form(
            step_id="add_usage_point",
            data_schema=vol.Schema({vol.Required(CONF_IDENTIFIKATOR): str}),
            errors=errors,
        )

    async def async_step_configure_measurements(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        rt_names = [rt.name for rt in KNOWN_READING_TYPES]
        if user_input is not None:
            self._pending_point[CONF_ROUTING] = {
                name: list(user_input.get(name) or []) for name in rt_names
            }
            if self._editing_index is not None:
                self._data[CONF_USAGE_POINTS][self._editing_index] = self._pending_point
            else:
                self._data[CONF_USAGE_POINTS].append(self._pending_point)
            self._pending_point = {}
            self._editing_index = None
            return await self._after_configure_point()
        existing = cast("Mapping[str, list[str]]", self._pending_point.get(CONF_ROUTING, {}))
        return self.async_show_form(
            step_id="configure_measurements",
            data_schema=_routing_schema(existing),
            description_placeholders={
                CONF_IDENTIFIKATOR: self._pending_point.get(CONF_IDENTIFIKATOR, ""),
                CONF_NAZIV: self._pending_point.get(CONF_NAZIV, ""),
            },
        )

    async def async_step_influxdb_version(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the InfluxDB API version, then branch to the matching form."""
        if user_input is not None:
            if user_input[CONF_INFLUXDB_API_VERSION] == INFLUXDB_V1:
                return await self.async_step_influxdb_config_v1()
            return await self.async_step_influxdb_config()
        existing = cast("Mapping[str, Any]", self._data.get(CONF_INFLUXDB) or {})
        default = existing.get(CONF_INFLUXDB_API_VERSION, INFLUXDB_V2)
        return self.async_show_form(
            step_id="influxdb_version",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INFLUXDB_API_VERSION, default=default
                    ): _INFLUXDB_VERSION_SELECTOR,
                }
            ),
        )

    async def async_step_influxdb_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """InfluxDB 2.x form: org / bucket / token."""
        existing = cast("Mapping[str, Any]", self._data.get(CONF_INFLUXDB) or {})
        if not existing:
            # Look for defaults in this priority order:
            #   1. HA's built-in InfluxDB integration (any v2 ConfigEntry)
            #   2. Environment variables on the HA process (set in
            #      docker/compose.yaml for the dev stack)
            # That way users who already configured one don't re-type, and
            # the dev container starts with the form pre-filled.
            shared = _read_ha_influxdb_entry(self.hass) or _read_env_influxdb()
            if shared is not None:
                existing = shared
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                count = await _validate_influxdb(self.hass, user_input)
            except InfluxDBAuthError:
                errors["base"] = "invalid_influx_auth"
            except InfluxDBConnectionError:
                errors["base"] = "cannot_connect_influx"
            except InfluxDBError:
                errors["base"] = "unknown_influx"
            else:
                self._data[CONF_INFLUXDB] = {
                    CONF_INFLUXDB_API_VERSION: INFLUXDB_V2,
                    **user_input,
                }
                self._influxdb_point_count = count
                return self._finish()
        return self.async_show_form(
            step_id="influxdb_config",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INFLUXDB_URL,
                        default=existing.get(CONF_INFLUXDB_URL, "http://influxdb:8086"),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_ORG,
                        default=existing.get(CONF_INFLUXDB_ORG, "home"),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_BUCKET,
                        default=existing.get(CONF_INFLUXDB_BUCKET, "elektro"),
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_TOKEN,
                        default=existing.get(CONF_INFLUXDB_TOKEN, ""),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_influxdb_config_v1(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """InfluxDB 1.x form (HA InfluxDB add-on): database / user / password.

        Fields are composed into the v2 shape the sink speaks, so nothing
        downstream needs to know which version the user picked.
        """
        existing = cast("Mapping[str, Any]", self._data.get(CONF_INFLUXDB) or {})
        prefill = (
            _decompose_v1(existing)
            if existing.get(CONF_INFLUXDB_API_VERSION) == INFLUXDB_V1
            else {}
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            composed = _compose_v1(user_input)
            try:
                count = await _validate_influxdb(self.hass, composed)
            except InfluxDBAuthError:
                errors["base"] = "invalid_influx_auth"
            except InfluxDBConnectionError:
                errors["base"] = "cannot_connect_influx"
            except InfluxDBDatabaseNotFound:
                errors[CONF_INFLUXDB_DATABASE] = "unknown_database"
            except InfluxDBError:
                errors["base"] = "unknown_influx"
            else:
                self._data[CONF_INFLUXDB] = composed
                self._influxdb_point_count = count
                return self._finish()
        return self.async_show_form(
            step_id="influxdb_config_v1",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INFLUXDB_URL,
                        default=prefill.get(CONF_INFLUXDB_URL) or _V1_DEFAULT_URL,
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_DATABASE,
                        default=prefill.get(CONF_INFLUXDB_DATABASE) or _V1_DEFAULT_DATABASE,
                    ): str,
                    vol.Optional(
                        CONF_INFLUXDB_RETENTION,
                        default=prefill.get(CONF_INFLUXDB_RETENTION) or DEFAULT_INFLUXDB_RETENTION,
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_USERNAME,
                        default=prefill.get(CONF_INFLUXDB_USERNAME) or _V1_DEFAULT_USERNAME,
                    ): str,
                    vol.Required(
                        CONF_INFLUXDB_PASSWORD,
                        default=prefill.get(CONF_INFLUXDB_PASSWORD) or "",
                    ): _PASSWORD_SELECTOR,
                }
            ),
            errors=errors,
        )

    def _finish(self) -> ConfigFlowResult:
        raise NotImplementedError


def _create_entry_result(
    flow: _FlowStepsMixin,
    *,
    title: str,
    data: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
) -> ConfigFlowResult:
    count = flow._influxdb_point_count
    flow._influxdb_point_count = None
    kwargs: dict[str, Any] = {"title": title, "data": data}
    if options is not None:
        kwargs["options"] = options
    if count is not None:
        kwargs["description"] = "influxdb_verified"
        kwargs["description_placeholders"] = {"count": str(count)}
    return flow.async_create_entry(**kwargs)


class MojElektroConfigFlow(_FlowStepsMixin, config_entries.ConfigFlow, domain=DOMAIN):
    # v2: per-reading-type routing is a list of sink names ({rt: [sink, ...]}).
    # Entries on disk already carry version 2; keep this in sync with them.
    VERSION = 2

    def __init__(self) -> None:
        self._data = {}
        self._pending_point = {}
        self._editing_index = None
        self._influxdb_point_count = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {
                CONF_TOKEN: user_input[CONF_TOKEN],
                CONF_SERVER: user_input[CONF_SERVER],
                CONF_USAGE_POINTS: [],
            }
            return await self.async_step_add_usage_point()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Required(CONF_SERVER, default=SERVER_PROD): vol.In(
                        [SERVER_PROD, SERVER_TEST]
                    ),
                }
            ),
        )

    async def _after_configure_point(self) -> ConfigFlowResult:
        # Single-meter constraint: no `add_another` step. If the user enabled
        # InfluxDB on any row and the connection isn't captured yet, run that
        # step now; otherwise we're done.
        if (
            _routing_uses_influxdb(self._data[CONF_USAGE_POINTS])
            and CONF_INFLUXDB not in self._data
        ):
            return await self.async_step_influxdb_version()
        return self._finish()

    def _finish(self) -> ConfigFlowResult:
        return _create_entry_result(
            self,
            title=_entry_title(self._data),
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> MojElektroOptionsFlow:
        return MojElektroOptionsFlow(entry)


class MojElektroOptionsFlow(_FlowStepsMixin, config_entries.OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self._data = dict(entry.data)
        self._data[CONF_USAGE_POINTS] = [dict(up) for up in self._data.get(CONF_USAGE_POINTS, [])]
        self._pending_point = {}
        self._editing_index = None
        self._influxdb_point_count = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # No usage point yet (interrupted setup) — re-add one.
        if not self._data.get(CONF_USAGE_POINTS):
            return await self.async_step_add_usage_point()
        # Each entry has exactly one merilno mesto; "edit" goes straight to it.
        options = ["edit_measurements", "sync_schedule", "backfill"]
        if _routing_uses_influxdb(self._data[CONF_USAGE_POINTS]):
            options.append("influxdb_version")
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_sync_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Turn the daily sync on/off and pick the local time it runs at."""
        if user_input is not None:
            self._data[CONF_SYNC_ENABLED] = bool(user_input[CONF_SYNC_ENABLED])
            self._data[CONF_SYNC_TIME] = user_input[CONF_SYNC_TIME]
            return self._finish()
        return self.async_show_form(
            step_id="sync_schedule",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SYNC_ENABLED,
                        default=self._data.get(CONF_SYNC_ENABLED, DEFAULT_SYNC_ENABLED),
                    ): _BOOL_SELECTOR,
                    vol.Required(
                        CONF_SYNC_TIME,
                        default=self._data.get(CONF_SYNC_TIME, DEFAULT_SYNC_TIME),
                    ): _TIME_SELECTOR,
                }
            ),
        )

    async def async_step_edit_measurements(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._editing_index = 0
        self._pending_point = dict(self._data[CONF_USAGE_POINTS][0])
        return await self.async_step_configure_measurements()

    async def async_step_backfill(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-fetch every routed measurement from a chosen date up to now.

        Runs in the background so the form returns immediately. Idempotent —
        Statistics upsert on `(statistic_id, hour)` and InfluxDB upserts on
        `(measurement, tag-set, timestamp)`.
        """
        if user_input is not None:
            start = _parse_date(user_input[CONF_BACKFILL_FROM])
            coord = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
            if start is not None and coord is not None:
                self.hass.async_create_task(coord.async_backfill_from(start))
            # Backfill doesn't change entry.data; close the dialog immediately.
            return self._finish()
        return self.async_show_form(
            step_id="backfill",
            data_schema=vol.Schema({vol.Required(CONF_BACKFILL_FROM): _DATE_SELECTOR}),
        )

    async def _after_configure_point(self) -> ConfigFlowResult:
        # Every sub-step writes through to entry.data and closes the dialog —
        # no separate "Save" button needed in the menu.
        return self._finish()

    def _finish(self) -> ConfigFlowResult:
        # Keep the entry title in sync with the usage point's naziv.
        self.hass.config_entries.async_update_entry(
            self.entry, data=self._data, title=_entry_title(self._data)
        )
        return _create_entry_result(self, title="", data={})


def _entry_title(data: Mapping[str, Any]) -> str:
    """Pick a config-entry title from the (single) usage point's naziv.

    Falls back to the identifikator, then to the integration's generic name —
    never returns empty since HA renders the title in the Devices & Services
    list and an empty string looks broken.
    """
    points = data.get(CONF_USAGE_POINTS) or []
    if points:
        first = points[0]
        candidate = first.get(CONF_NAZIV) or first.get(CONF_IDENTIFIKATOR)
        if candidate:
            return str(candidate)
    return "Moj Elektro"


def _read_env_influxdb() -> dict[str, str] | None:
    """Read InfluxDB defaults from env vars (see _ENV_INFLUXDB).

    Returns None if no env vars are set. If at least one is set, returns
    every key (env-missing ones become empty strings, which the form will
    surface as blank fields the user still has to fill).
    """
    values = {key: os.environ.get(var, "") for key, var in _ENV_INFLUXDB.items()}
    if not any(values.values()):
        return None
    return values


def _read_ha_influxdb_entry(hass: HomeAssistant) -> dict[str, str] | None:
    """Pull URL/org/bucket/token from HA's built-in InfluxDB integration if set up.

    HA stores InfluxDB v2 credentials in a ConfigEntry of domain `influxdb`.
    We translate its host/port/ssl back into a URL and return the same dict
    shape our own form uses, so it can be passed straight in as defaults.
    Returns None if no v2 entry is configured.
    """
    for entry in hass.config_entries.async_entries("influxdb"):
        data = entry.data
        if data.get("api_version") != 2:
            continue
        host = data.get("host") or "localhost"
        port = int(data.get("port") or 8086)
        scheme = "https" if data.get("ssl") else "http"
        return {
            CONF_INFLUXDB_URL: f"{scheme}://{host}:{port}",
            CONF_INFLUXDB_ORG: str(data.get("organization") or ""),
            CONF_INFLUXDB_BUCKET: str(data.get("bucket") or ""),
            CONF_INFLUXDB_TOKEN: str(data.get("token") or ""),
        }
    return None


def _parse_date(value: str | date) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return None


async def _validate_influxdb(
    hass: HomeAssistant, config: Mapping[str, str]
) -> int:
    """Probe InfluxDB and return how many ``mojelektro`` points already exist."""
    http = await hass.async_add_executor_job(httpx.AsyncClient)
    try:
        return await probe_influxdb_connection(
            http,
            url=config[CONF_INFLUXDB_URL],
            org=config.get(CONF_INFLUXDB_ORG, ""),
            bucket=config[CONF_INFLUXDB_BUCKET],
            token=config[CONF_INFLUXDB_TOKEN],
            api_version=config.get(CONF_INFLUXDB_API_VERSION, INFLUXDB_V2),
        )
    finally:
        await http.aclose()
