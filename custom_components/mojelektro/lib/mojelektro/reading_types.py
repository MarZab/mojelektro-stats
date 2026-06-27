"""Typed constants for the Moj Elektro reading-type catalog.

GENERATED FILE. Do not edit by hand. Regenerate with:
    make regen-reading-types

Source: tests/lib/cassettes/test_client_recorded/test_recorded_reading_types.yaml
Catalog size: 20 reading types
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReadingTypeCode(StrEnum):
    """API option-parameter values, ready to pass into
    `MojElektroClient.get_meter_readings(..., options=[...])`.
    """

    A_PLUS_15MIN = "ReadingType=32.0.2.4.1.2.12.0.0.0.0.0.0.0.0.3.72.0"
    A_MINUS_15MIN = "ReadingType=32.0.2.4.19.2.12.0.0.0.0.0.0.0.0.3.72.0"
    R_PLUS_15MIN = "ReadingType=32.0.2.4.1.2.12.0.0.0.0.0.0.0.0.3.73.0"
    R_MINUS_15MIN = "ReadingType=32.0.2.4.19.2.12.0.0.0.0.0.0.0.0.3.73.0"
    P_PLUS_15MIN = "ReadingType=32.0.2.4.1.2.37.0.0.0.0.0.0.0.0.3.38.0"
    P_MINUS_15MIN = "ReadingType=32.0.2.4.19.2.37.0.0.0.0.0.0.0.0.3.38.0"
    Q_PLUS_15MIN = "ReadingType=32.0.2.4.1.2.37.0.0.0.0.0.0.0.0.3.63.0"
    Q_MINUS_15MIN = "ReadingType=32.0.2.4.19.2.37.0.0.0.0.0.0.0.0.3.63.0"
    A_PLUS_T0_DAILY = "ReadingType=32.0.4.1.1.2.12.0.0.0.0.0.0.0.0.3.72.0"
    A_PLUS_T1_DAILY = "ReadingType=32.0.4.1.1.2.12.0.0.0.0.1.0.0.0.3.72.0"
    A_PLUS_T2_DAILY = "ReadingType=32.0.4.1.1.2.12.0.0.0.0.2.0.0.0.3.72.0"
    A_MINUS_T0_DAILY = "ReadingType=32.0.4.1.19.2.12.0.0.0.0.0.0.0.0.3.72.0"
    A_MINUS_T1_DAILY = "ReadingType=32.0.4.1.19.2.12.0.0.0.0.1.0.0.0.3.72.0"
    A_MINUS_T2_DAILY = "ReadingType=32.0.4.1.19.2.12.0.0.0.0.2.0.0.0.3.72.0"
    R_PLUS_T0_DAILY = "ReadingType=32.0.4.1.1.2.12.0.0.0.0.0.0.0.0.3.73.0"
    R_PLUS_T1_DAILY = "ReadingType=32.0.4.1.1.2.12.0.0.0.0.1.0.0.0.3.73.0"
    R_PLUS_T2_DAILY = "ReadingType=32.0.4.1.1.2.12.0.0.0.0.2.0.0.0.3.73.0"
    R_MINUS_T0_DAILY = "ReadingType=32.0.4.1.19.2.12.0.0.0.0.0.0.0.0.3.73.0"
    R_MINUS_T1_DAILY = "ReadingType=32.0.4.1.19.2.12.0.0.0.0.1.0.0.0.3.73.0"
    R_MINUS_T2_DAILY = "ReadingType=32.0.4.1.19.2.12.0.0.0.0.2.0.0.0.3.73.0"


@dataclass(frozen=True, slots=True)
class ReadingTypeInfo:
    """Catalog metadata for a known reading type."""

    name: str
    oznaka: str
    perioda: str
    tip: str
    vrsta: str
    opis: str
    code: ReadingTypeCode
    naziv: str = ""  # API description; "" if cassette is pre-scrub-refactor


KNOWN_READING_TYPES: tuple[ReadingTypeInfo, ...] = (
    ReadingTypeInfo(
        name="A_PLUS_15MIN",
        oznaka="A+",
        perioda="15 min",
        tip="delovna prejem",
        vrsta="KOLICINA",
        opis="15 minutna energija, A+, kWh",
        code=ReadingTypeCode.A_PLUS_15MIN,
        naziv="Prejeta 15 minutna delovna energija",
    ),
    ReadingTypeInfo(
        name="A_MINUS_15MIN",
        oznaka="A-",
        perioda="15 min",
        tip="delovna oddaja",
        vrsta="KOLICINA",
        opis="15 minutna energija, A-, kWh",
        code=ReadingTypeCode.A_MINUS_15MIN,
        naziv="Oddana 15 minutna delovna energija",
    ),
    ReadingTypeInfo(
        name="R_PLUS_15MIN",
        oznaka="R+",
        perioda="15 min",
        tip="jalova prejem",
        vrsta="KOLICINA",
        opis="15 minutna energija, R+, kVArh",
        code=ReadingTypeCode.R_PLUS_15MIN,
        naziv="Prejeta 15 minutna jalova energija",
    ),
    ReadingTypeInfo(
        name="R_MINUS_15MIN",
        oznaka="R-",
        perioda="15 min",
        tip="jalova oddaja",
        vrsta="KOLICINA",
        opis="15 minutna energija, R-, kVArh",
        code=ReadingTypeCode.R_MINUS_15MIN,
        naziv="Oddana 15 minutna jalova energija",
    ),
    ReadingTypeInfo(
        name="P_PLUS_15MIN",
        oznaka="P+",
        perioda="15 min",
        tip="delovna prejem",
        vrsta="KOLICINA",
        opis="15 minutna moč, A+, kW",
        code=ReadingTypeCode.P_PLUS_15MIN,
        naziv="Prejeta 15 minutna delovna moč",
    ),
    ReadingTypeInfo(
        name="P_MINUS_15MIN",
        oznaka="P-",
        perioda="15 min",
        tip="delovna oddaja",
        vrsta="KOLICINA",
        opis="15 minutna moč, A-, kW",
        code=ReadingTypeCode.P_MINUS_15MIN,
        naziv="Oddana 15 minutna delovna moč",
    ),
    ReadingTypeInfo(
        name="Q_PLUS_15MIN",
        oznaka="Q+",
        perioda="15 min",
        tip="jalova prejem",
        vrsta="KOLICINA",
        opis="15 minutna moč, R+, kVAr",
        code=ReadingTypeCode.Q_PLUS_15MIN,
        naziv="Prejeta 15 minutna jalova moč",
    ),
    ReadingTypeInfo(
        name="Q_MINUS_15MIN",
        oznaka="Q-",
        perioda="15 min",
        tip="jalova oddaja",
        vrsta="KOLICINA",
        opis="15 minutna moč, R-, kVAr",
        code=ReadingTypeCode.Q_MINUS_15MIN,
        naziv="Oddana 15 minutna jalova moč",
    ),
    ReadingTypeInfo(
        name="A_PLUS_T0_DAILY",
        oznaka="A+_T0",
        perioda="24 h",
        tip="delovna prejem ET",
        vrsta="STANJE",
        opis="24 urno stanje, A+, kWh, T0",
        code=ReadingTypeCode.A_PLUS_T0_DAILY,
        naziv="Prejeta delovna energija ET",
    ),
    ReadingTypeInfo(
        name="A_PLUS_T1_DAILY",
        oznaka="A+_T1",
        perioda="24 h",
        tip="delovna prejem VT",
        vrsta="STANJE",
        opis="24 urno stanje, A+, kWh, T1",
        code=ReadingTypeCode.A_PLUS_T1_DAILY,
        naziv="Prejeta delovna energija VT",
    ),
    ReadingTypeInfo(
        name="A_PLUS_T2_DAILY",
        oznaka="A+_T2",
        perioda="24 h",
        tip="delovna prejem MT",
        vrsta="STANJE",
        opis="24 urno stanje, A+, kWh, T2",
        code=ReadingTypeCode.A_PLUS_T2_DAILY,
        naziv="Prejeta delovna energija MT",
    ),
    ReadingTypeInfo(
        name="A_MINUS_T0_DAILY",
        oznaka="A-_T0",
        perioda="24 h",
        tip="delovna oddaja ET",
        vrsta="STANJE",
        opis="24 urno stanje, A-, kWh, T0",
        code=ReadingTypeCode.A_MINUS_T0_DAILY,
        naziv="Oddana delovna energija ET",
    ),
    ReadingTypeInfo(
        name="A_MINUS_T1_DAILY",
        oznaka="A-_T1",
        perioda="24 h",
        tip="delovna oddaja VT",
        vrsta="STANJE",
        opis="24 urno stanje, A-, kWh, T1",
        code=ReadingTypeCode.A_MINUS_T1_DAILY,
        naziv="Oddana delovna energija VT",
    ),
    ReadingTypeInfo(
        name="A_MINUS_T2_DAILY",
        oznaka="A-_T2",
        perioda="24 h",
        tip="delovna oddaja MT",
        vrsta="STANJE",
        opis="24 urno stanje, A-, kWh, T2",
        code=ReadingTypeCode.A_MINUS_T2_DAILY,
        naziv="Oddana delovna energija MT",
    ),
    ReadingTypeInfo(
        name="R_PLUS_T0_DAILY",
        oznaka="R+_T0",
        perioda="24 h",
        tip="jalova prejem ET",
        vrsta="STANJE",
        opis="24 urno stanje, R+, kVArh, T0",
        code=ReadingTypeCode.R_PLUS_T0_DAILY,
        naziv="Prejeta jalova energija ET",
    ),
    ReadingTypeInfo(
        name="R_PLUS_T1_DAILY",
        oznaka="R+_T1",
        perioda="24 h",
        tip="jalova prejem VT",
        vrsta="STANJE",
        opis="24 urno stanje, R+, kVArh, T1",
        code=ReadingTypeCode.R_PLUS_T1_DAILY,
        naziv="Prejeta jalova energija VT",
    ),
    ReadingTypeInfo(
        name="R_PLUS_T2_DAILY",
        oznaka="R+_T2",
        perioda="24 h",
        tip="jalova prejem MT",
        vrsta="STANJE",
        opis="24 urno stanje, R+, kVArh, T2",
        code=ReadingTypeCode.R_PLUS_T2_DAILY,
        naziv="Prejeta jalova energija MT",
    ),
    ReadingTypeInfo(
        name="R_MINUS_T0_DAILY",
        oznaka="R-_T0",
        perioda="24 h",
        tip="jalova oddaja ET",
        vrsta="STANJE",
        opis="24 urno stanje, R-, kVArh, T0",
        code=ReadingTypeCode.R_MINUS_T0_DAILY,
        naziv="Oddana jalova energija ET",
    ),
    ReadingTypeInfo(
        name="R_MINUS_T1_DAILY",
        oznaka="R-_T1",
        perioda="24 h",
        tip="jalova oddaja VT",
        vrsta="STANJE",
        opis="24 urno stanje, R-, kVArh, T1",
        code=ReadingTypeCode.R_MINUS_T1_DAILY,
        naziv="Oddana jalova energija VT",
    ),
    ReadingTypeInfo(
        name="R_MINUS_T2_DAILY",
        oznaka="R-_T2",
        perioda="24 h",
        tip="jalova oddaja MT",
        vrsta="STANJE",
        opis="24 urno stanje, R-, kVArh, T2",
        code=ReadingTypeCode.R_MINUS_T2_DAILY,
        naziv="Oddana jalova energija MT",
    ),
)


BY_NAME: dict[str, ReadingTypeInfo] = {rt.name: rt for rt in KNOWN_READING_TYPES}
BY_OZNAKA: dict[str, tuple[ReadingTypeInfo, ...]] = {
    oznaka: tuple(rt for rt in KNOWN_READING_TYPES if rt.oznaka == oznaka)
    for oznaka in {rt.oznaka for rt in KNOWN_READING_TYPES}
}
# Keyed by the raw code (no `ReadingType=` prefix) — used to look up
# catalog metadata for the readingType field returned in API responses.
BY_RAW_CODE: dict[str, ReadingTypeInfo] = {
    rt.code.value.removeprefix("ReadingType="): rt for rt in KNOWN_READING_TYPES
}

__all__ = [
    "BY_NAME",
    "BY_OZNAKA",
    "BY_RAW_CODE",
    "KNOWN_READING_TYPES",
    "ReadingTypeCode",
    "ReadingTypeInfo",
]
