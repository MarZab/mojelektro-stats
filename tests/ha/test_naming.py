from __future__ import annotations

import pytest
from homeassistant.util.unit_conversion import (
    EnergyConverter,
    PowerConverter,
    ReactiveEnergyConverter,
    ReactivePowerConverter,
)

from custom_components.mojelektro_stats._naming import slug_reading_type, unit, unit_class
from mojelektro_api import KNOWN_READING_TYPES

_CONVERTERS = {
    "energy": EnergyConverter,
    "reactive_energy": ReactiveEnergyConverter,
    "power": PowerConverter,
    "reactive_power": ReactivePowerConverter,
}


@pytest.mark.ha
def test_reading_type_slugs_are_unique() -> None:
    """Every reading type must map to a distinct statistic slug.

    The statistic_id is derived from this slug, so a collision would make two
    reading types share one statistic_id and silently overwrite each other —
    e.g. if the tariff suffix (T0/T1/T2) were ever dropped from the slug.
    """
    slugs = [slug_reading_type(rt).replace("-", "_") for rt in KNOWN_READING_TYPES]
    assert len(slugs) == len(set(slugs)), "duplicate statistic slugs: " + ", ".join(
        s for s in slugs if slugs.count(s) > 1
    )


@pytest.mark.ha
def test_units_are_valid_for_their_unit_class() -> None:
    """Each reading type's unit must be accepted by HA for its unit_class.

    HA rejects statistics whose unit_of_measurement doesn't match the
    unit_class (e.g. "kVArh" is invalid for "reactive_energy"; it must be
    "kvarh"), which blocks setup. Guard against the wrong casing/spelling.
    """
    bad = []
    for rt in KNOWN_READING_TYPES:
        u = unit(rt)
        uc = unit_class(rt)
        if uc is None:
            continue
        valid = {str(x) for x in _CONVERTERS[uc].VALID_UNITS}
        if u not in valid:
            bad.append(f"{rt.name}: {u!r} not in {uc} {sorted(valid)}")
    assert not bad, "invalid unit/unit_class pairs:\n" + "\n".join(bad)
