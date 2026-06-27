from __future__ import annotations

from mojelektro.models import (
    IntervalBlock,
    IntervalReading,
    MerilnaTocka,
    MerilnaTockaRef,
    MerilnoMesto,
    MeterReadings,
    Server,
)


def test_server_urls() -> None:
    assert Server.PRODUCTION.base_url == "https://api.informatika.si/mojelektro/v1"
    assert Server.TEST.base_url == "https://api-test.informatika.si/mojelektro/v1"


def test_typed_dict_aliases_are_dicts() -> None:
    # TypedDicts are runtime-equivalent to dict; the lib returns parsed JSON
    # straight through, so consumers can treat values as plain dicts/lists.
    reading: IntervalReading = {"timestamp": "2026-06-06T00:00:00Z", "value": "1.23"}
    block: IntervalBlock = {"readingType": "ReadingType=X", "intervalReadings": [reading]}
    readings: MeterReadings = {"usagePoint": "GSRN", "intervalBlocks": [block]}
    mm: MerilnoMesto = {
        "gsrn": "100000000000000000",
        "merilneTocke": [MerilnaTockaRef(gsrn="200000000000000000", vrsta="OMTO")],
    }
    mt: MerilnaTocka = {"anything": "goes"}
    assert readings["intervalBlocks"][0]["readingType"] == "ReadingType=X"
    assert mm["merilneTocke"][0]["vrsta"] == "OMTO"
    assert mt["anything"] == "goes"
