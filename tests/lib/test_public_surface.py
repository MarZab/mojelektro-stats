from __future__ import annotations


def test_public_surface() -> None:
    import mojelektro

    expected = {
        "MojElektroClient",
        "MojElektroError",
        "AuthError",
        "NotFoundError",
        "InvalidRequestError",
        "TransportError",
        "MeterReadings",
        "MerilnoMesto",
        "MerilnaTocka",
        "Server",
        "KNOWN_READING_TYPES",
        "ReadingTypeCode",
        "ReadingTypeInfo",
    }
    assert expected <= set(mojelektro.__all__)
    for name in expected:
        assert hasattr(mojelektro, name), name


def test_reading_types_endpoints_not_exposed() -> None:
    """`ReadingType` and `ReadingQuality` were dropped — the lib no longer
    fetches the catalog at runtime. `KNOWN_READING_TYPES` is the catalog."""
    import mojelektro

    for gone in ("ReadingType", "ReadingQuality"):
        assert gone not in mojelektro.__all__
        assert not hasattr(mojelektro, gone)
