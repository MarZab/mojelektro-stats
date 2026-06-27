"""Slug + unit derivation for reading types.

The Moj Elektro reading-type catalog is hardcoded in the lib (one entry per
ReadingTypeCode). Here we convert each entry into the things the sinks need:
- a stable URL-safe slug for statistic IDs and InfluxDB tags;
- the HA unit (kWh / kW / kvarh / kvar) for statistics metadata.

Catalog-derived. If the catalog regenerates, run the tests; if a new reading
type appears that this module doesn't recognize, `unit()` returns None and
the sink still works without a unit.
"""

from __future__ import annotations

from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
)

from custom_components.mojelektro_stats import _bootstrap  # noqa: F401
from mojelektro_api import ReadingTypeInfo


def slug_usage_point(identifikator: str) -> str:
    """Strip dashes from the short identifikator, e.g. `4-1234567` -> `41234567`."""
    return identifikator.replace("-", "")


def slug_reading_type(info: ReadingTypeInfo) -> str:
    """Compact lowercase slug from a `ReadingTypeInfo.name`.

    Examples:
        A_PLUS_15MIN     -> "a-plus-15"
        A_PLUS_T0_DAILY  -> "a-plus-t0"
        R_MINUS_T2_DAILY -> "r-minus-t2"
    """
    parts = info.name.lower().split("_")
    last = parts[-1]
    if last == "daily":
        parts = parts[:-1]
    elif last.endswith("min"):
        parts[-1] = last.removesuffix("min")
    return "-".join(parts)


def unit(info: ReadingTypeInfo) -> str | None:
    """Return the HA unit string for a reading type, or None if unknown.

    A_/R_ -> kWh / kvarh (energy). P_/Q_ -> kW / kvar (power).

    HA validates the unit string against the unit_class, so these must be the
    canonical HA unit constants (e.g. ``kvarh``, not ``kVArh``).
    """
    prefix = info.name.split("_", 1)[0]
    if prefix == "A":
        return UnitOfEnergy.KILO_WATT_HOUR
    if prefix == "R":
        return UnitOfReactiveEnergy.KILO_VOLT_AMPERE_REACTIVE_HOUR
    if prefix == "P":
        return UnitOfPower.KILO_WATT
    if prefix == "Q":
        return UnitOfReactivePower.KILO_VOLT_AMPERE_REACTIVE
    return None


def unit_class(info: ReadingTypeInfo) -> str | None:
    """Return the HA `unit_class` for a reading type.

    Required for HA's Energy dashboard to show the statistic in its picker
    (the dropdown filters by `unit_class="energy"`). Maps:
        A_* -> "energy"            (kWh)
        R_* -> "reactive_energy"   (kvarh)
        P_* -> "power"             (kW)
        Q_* -> "reactive_power"    (kvar)
    """
    prefix = info.name.split("_", 1)[0]
    if prefix == "A":
        return "energy"
    if prefix == "R":
        return "reactive_energy"
    if prefix == "P":
        return "power"
    if prefix == "Q":
        return "reactive_power"
    return None
