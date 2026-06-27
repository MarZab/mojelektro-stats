"""Pure-routing dispatcher.

Takes the API's `MeterReadings` response for one usage point plus the user's
per-measurement routing, and fans each interval block out to every sink the
user enabled for that reading type. No I/O of its own — sinks own persistence.

Routing shape (entry data, post-v2): {reading_type_name: [sink_name, ...]}.
Empty list -> nothing to write. Unknown reading-type codes are dropped (the
catalog is hardcoded; an unknown code means the catalog is stale).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Final

from custom_components.mojelektro_stats import _bootstrap  # noqa: F401
from custom_components.mojelektro_stats.sinks import Sink
from mojelektro_api import BY_RAW_CODE, MeterReadings

_LOGGER: Final = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, sinks: dict[str, Sink]) -> None:
        self._sinks = sinks

    async def dispatch(
        self,
        usage_point: str,
        meter_readings: MeterReadings,
        routing: Mapping[str, list[str]],
        *,
        replace_window: tuple[date, date] | None = None,
    ) -> None:
        for block in meter_readings.get("intervalBlocks", []):
            raw_code = block.get("readingType", "")
            info = BY_RAW_CODE.get(raw_code)
            if info is None:
                _LOGGER.debug(
                    "Unknown reading type %r for usage point %s; "
                    "consider running `make regen-reading-types`",
                    raw_code,
                    usage_point,
                )
                continue
            for choice in routing.get(info.name, ()):
                sink = self._sinks.get(choice)
                if sink is None:
                    _LOGGER.warning(
                        "No sink registered for %r (routing for %s on %s); skipping",
                        choice,
                        info.name,
                        usage_point,
                    )
                    continue
                await sink.write(
                    usage_point,
                    info,
                    block.get("intervalReadings", []),
                    replace_window=replace_window,
                )
