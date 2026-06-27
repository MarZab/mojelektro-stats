"""DataUpdateCoordinator for the Moj Elektro integration.

Per-day poll. Per-usage-point window `[last_synced_end, cutoff)` where
`cutoff = now - 4h` (the API publishes prior-day data; recent intervals may
still be unstable). Half-open at the upper end; first sync starts
`backfill_days` before the cutoff.

Per-point error isolation: a fetch failure on one usage point does not stop
the others, but the coordinator surfaces an `UpdateFailed` at the end if any
point failed. `last_synced_end` for a point only advances after its dispatch
completes without errors — so retries are idempotent.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator, Mapping
from datetime import date, timedelta
from typing import Any, Final

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.mojelektro import _bootstrap  # noqa: F401
from custom_components.mojelektro.const import (
    CONF_IDENTIFIKATOR,
    CONF_ROUTING,
    DEFAULT_BACKFILL_DAYS,
    DOMAIN,
    MAX_FETCH_WINDOW_DAYS,
    SYNC_CUTOFF_HOURS,
)
from custom_components.mojelektro.dispatcher import Dispatcher
from mojelektro import (
    BY_NAME,
    AuthError,
    InvalidRequestError,
    MojElektroClient,
    NotFoundError,
    TransportError,
)

_LOGGER: Final = logging.getLogger(__name__)
_UPDATE_INTERVAL: Final = timedelta(days=1)
_PER_POINT_TIMEOUT_S: Final = 60


class MojElektroDataUpdateCoordinator(DataUpdateCoordinator[None]):
    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: MojElektroClient,
        usage_points: list[Mapping[str, Any]],
        dispatcher: Dispatcher,
        last_synced_end: Mapping[str, date] | None = None,
        backfill_days: int = DEFAULT_BACKFILL_DAYS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=_UPDATE_INTERVAL,
        )
        self.client = client
        self.usage_points = list(usage_points)
        self.dispatcher = dispatcher
        self.last_synced_end: dict[str, date] = dict(last_synced_end or {})
        self.backfill_days = backfill_days

    async def _async_update_data(self) -> None:
        now = dt_util.utcnow()
        cutoff_dt = now - timedelta(hours=SYNC_CUTOFF_HOURS)
        end_date = cutoff_dt.date()
        failures: list[BaseException] = []

        async def fetch_one(up: Mapping[str, Any]) -> None:
            gsrn = up[CONF_IDENTIFIKATOR]
            routing = up.get(CONF_ROUTING, {})
            start_date = (
                self.last_synced_end.get(gsrn)
                or (cutoff_dt - timedelta(days=self.backfill_days)).date()
            )
            if start_date >= end_date:
                return
            options = _routing_to_options(routing)
            if not options:
                self.last_synced_end[gsrn] = end_date
                return

            for chunk_start, chunk_end in _chunk_window(
                start_date, end_date, MAX_FETCH_WINDOW_DAYS
            ):
                try:
                    async with asyncio.timeout(_PER_POINT_TIMEOUT_S):
                        readings = await self.client.get_meter_readings(
                            gsrn, chunk_start, chunk_end, options=options
                        )
                except AuthError as exc:
                    raise ConfigEntryAuthFailed from exc
                except NotFoundError:
                    _LOGGER.warning("Usage point %s not found; skipping this cycle", gsrn)
                    return
                except (TransportError, InvalidRequestError) as exc:
                    _LOGGER.warning(
                        "Error fetching %s for %s..%s: %s",
                        gsrn,
                        chunk_start,
                        chunk_end,
                        exc,
                    )
                    failures.append(exc)
                    return

                try:
                    await self.dispatcher.dispatch(gsrn, readings, dict(routing))
                except Exception as exc:
                    _LOGGER.exception("Sink failure for %s", gsrn)
                    failures.append(exc)
                    return

                # Advance per chunk so a failure halfway through a long backfill
                # preserves progress and the next cycle resumes from here.
                self.last_synced_end[gsrn] = chunk_end

        if self.usage_points:
            await asyncio.gather(
                *(fetch_one(up) for up in self.usage_points), return_exceptions=False
            )

        if failures:
            raise UpdateFailed(str(failures[0]))

    async def async_backfill_from(self, start: date) -> int:
        """Manual backfill triggered from the OptionsFlow.

        Re-fetches every routed reading type for every usage point from `start`
        up to the current cutoff and dispatches through the configured sinks.
        Each chunk clears existing sink data in that window before re-import so
        stale or corrected API values replace what was stored earlier.
        Deliberately does NOT touch `last_synced_end` — this is an out-of-band
        operation that should not perturb the regular daily-sync cursor.

        Returns the number of API requests issued (one per (point, chunk))
        so the OptionsFlow can show a confirmation.
        """
        now = dt_util.utcnow()
        cutoff_dt = now - timedelta(hours=SYNC_CUTOFF_HOURS)
        end_date = cutoff_dt.date()
        if start >= end_date:
            return 0
        requests = 0
        for up in self.usage_points:
            gsrn = up[CONF_IDENTIFIKATOR]
            routing = up.get(CONF_ROUTING, {})
            options = _routing_to_options(routing)
            if not options:
                continue
            for chunk_start, chunk_end in _chunk_window(start, end_date, MAX_FETCH_WINDOW_DAYS):
                try:
                    async with asyncio.timeout(_PER_POINT_TIMEOUT_S):
                        readings = await self.client.get_meter_readings(
                            gsrn, chunk_start, chunk_end, options=options
                        )
                    await self.dispatcher.dispatch(
                        gsrn,
                        readings,
                        dict(routing),
                        replace_window=(chunk_start, chunk_end),
                    )
                except (
                    AuthError,
                    NotFoundError,
                    TransportError,
                    InvalidRequestError,
                ) as exc:
                    _LOGGER.warning(
                        "Backfill chunk %s..%s failed for %s: %s",
                        chunk_start,
                        chunk_end,
                        gsrn,
                        exc,
                    )
                requests += 1
        return requests


def _chunk_window(start: date, end: date, max_days: int) -> Iterator[tuple[date, date]]:
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=max_days), end)
        yield (cursor, chunk_end)
        cursor = chunk_end


def _routing_to_options(routing: Mapping[str, list[str]]) -> list[str]:
    """Translate the user's routing (keyed by ReadingTypeInfo.name) into the
    list of raw `ReadingType=...` codes to pass into `get_meter_readings`.

    A reading type with an empty sink list is omitted (nothing to fetch).
    """
    out: list[str] = []
    for name, sinks in routing.items():
        if not sinks:
            continue
        info = BY_NAME.get(name)
        if info is None:
            continue
        out.append(info.code.value)
    return out
