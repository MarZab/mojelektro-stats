"""Slug + unit derivation for reading types.

The Moj Elektro reading-type catalog is hardcoded in the lib (one entry per
ReadingTypeCode). Here we convert each entry into the things the sinks need:
- a stable URL-safe slug for statistic IDs and InfluxDB tags;
- the HA unit (kWh / kW / kVArh / kVAr) for statistics metadata.

Catalog-derived. If the catalog regenerates, run the tests; if a new reading
type appears that this module doesn't recognize, `unit()` returns None and
the sink still works without a unit.
"""

from __future__ import annotations

from typing import Final

from homeassistant.const import UnitOfEnergy, UnitOfPower

from custom_components.mojelektro import _bootstrap  # noqa: F401
from mojelektro import ReadingTypeInfo

_UNIT_KVARH: Final = "kVArh"
_UNIT_KVAR: Final = "kVAr"


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

    A_/R_ -> kWh / kVArh (energy). P_/Q_ -> kW / kVAr (power).
    """
    prefix = info.name.split("_", 1)[0]
    if prefix == "A":
        return UnitOfEnergy.KILO_WATT_HOUR
    if prefix == "R":
        return _UNIT_KVARH
    if prefix == "P":
        return UnitOfPower.KILO_WATT
    if prefix == "Q":
        return _UNIT_KVAR
    return None


def unit_class(info: ReadingTypeInfo) -> str | None:
    """Return the HA `unit_class` for a reading type.

    Required for HA's Energy dashboard to show the statistic in its picker
    (the dropdown filters by `unit_class="energy"`). Maps:
        A_* -> "energy"            (kWh)
        R_* -> "reactive_energy"   (kVArh)
        P_* -> "power"             (kW)
        Q_* -> "reactive_power"    (kVAr)
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
