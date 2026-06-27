from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict


class Server(StrEnum):
    PRODUCTION = "https://api.informatika.si/mojelektro/v1"
    TEST = "https://api-test.informatika.si/mojelektro/v1"

    @property
    def base_url(self) -> str:
        return self.value


class IntervalReading(TypedDict, total=False):
    timestamp: str
    value: str


class IntervalBlock(TypedDict, total=False):
    readingType: str
    intervalReadings: list[IntervalReading]


class MeterReadings(TypedDict, total=False):
    usagePoint: str
    intervalBlocks: list[IntervalBlock]


class MerilnaTockaRef(TypedDict, total=False):
    gsrn: str
    vrsta: str


class _Identifikator(TypedDict, total=False):
    gsrn: str
    enotniIdentifikatorMerilnegaMesta: str


class MerilnoMesto(TypedDict, total=False):
    identifikator: _Identifikator
    enotniIdentifikatorMerilnegaMesta: str
    gsrn: str
    merilneTocke: list[MerilnaTockaRef]


MerilnaTocka = dict[str, Any]


__all__ = [
    "IntervalBlock",
    "IntervalReading",
    "MerilnaTocka",
    "MerilnaTockaRef",
    "MerilnoMesto",
    "MeterReadings",
    "Server",
]
