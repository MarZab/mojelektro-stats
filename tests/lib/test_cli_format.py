from __future__ import annotations

import json
from typing import Any

import yaml

from cli._format import (
    OutputFormat,
    dump,
    dump_readings,
    flatten_to_pairs,
    pivot_readings,
)
from mojelektro.reading_types import ReadingTypeCode


def _payload() -> list[dict[str, Any]]:
    return [{"a": 1, "b": "two"}, {"a": 3, "b": "four"}]


def test_json_format_round_trip() -> None:
    out = dump(_payload(), OutputFormat.JSON)
    assert json.loads(out) == _payload()


def test_yaml_format_round_trip() -> None:
    out = dump(_payload(), OutputFormat.YAML)
    assert yaml.safe_load(out) == _payload()


def test_table_format_returns_non_empty_string() -> None:
    out = dump(_payload(), OutputFormat.TABLE)
    assert "a" in out
    assert "b" in out
    assert "two" in out


def test_json_handles_dict_payload() -> None:
    out = dump({"x": 1}, OutputFormat.JSON)
    assert json.loads(out) == {"x": 1}


def test_json_handles_non_serializable_via_default_str() -> None:
    from datetime import date

    out = dump({"d": date(2026, 6, 1)}, OutputFormat.JSON)
    assert json.loads(out) == {"d": "2026-06-01"}


def test_flatten_flat_dict() -> None:
    assert flatten_to_pairs({"a": 1, "b": "two"}) == [("a", "1"), ("b", "two")]


def test_flatten_nested_dict_uses_dot_paths() -> None:
    payload = {"gsrn": "X", "identifikator": {"gsrn": "Y", "code": "Z"}}
    assert flatten_to_pairs(payload) == [
        ("gsrn", "X"),
        ("identifikator.gsrn", "Y"),
        ("identifikator.code", "Z"),
    ]


def test_flatten_list_uses_indexed_paths() -> None:
    payload = {"merilneTocke": [{"gsrn": "A", "vrsta": "OMTO"}, {"gsrn": "B"}]}
    assert flatten_to_pairs(payload) == [
        ("merilneTocke.0.gsrn", "A"),
        ("merilneTocke.0.vrsta", "OMTO"),
        ("merilneTocke.1.gsrn", "B"),
    ]


def test_flatten_empty_containers_get_sentinel_value() -> None:
    assert flatten_to_pairs({"a": {}, "b": []}) == [("a", "{}"), ("b", "[]")]


def test_flatten_none_becomes_empty_string() -> None:
    assert flatten_to_pairs({"a": None}) == [("a", "")]


def test_table_format_for_dict_uses_flattened_paths() -> None:
    out = dump(
        {"gsrn": "X", "merilneTocke": [{"gsrn": "Y", "vrsta": "OMTO"}]},
        OutputFormat.TABLE,
    )
    assert "gsrn" in out
    assert "merilneTocke.0.gsrn" in out
    assert "merilneTocke.0.vrsta" in out
    assert "OMTO" in out
    # The whole nested object must NOT appear as a single repr-blob cell.
    assert "{'gsrn'" not in out
    assert "[{" not in out


def _two_block_payload() -> dict[str, Any]:
    a_plus = ReadingTypeCode.A_PLUS_15MIN.value.removeprefix("ReadingType=")
    a_minus = ReadingTypeCode.A_MINUS_15MIN.value.removeprefix("ReadingType=")
    return {
        "intervalBlocks": [
            {
                "readingType": a_plus,
                "intervalReadings": [
                    {"timestamp": "2026-06-01T00:15:00+02:00", "value": "0.5"},
                    {"timestamp": "2026-06-01T00:30:00+02:00", "value": "0.7"},
                ],
            },
            {
                "readingType": a_minus,
                "intervalReadings": [
                    {"timestamp": "2026-06-01T00:15:00+02:00", "value": "0.1"},
                    {"timestamp": "2026-06-01T00:45:00+02:00", "value": "0.2"},
                ],
            },
        ]
    }


def test_pivot_columns_use_oznaka() -> None:
    cols, _ = pivot_readings(_two_block_payload())
    assert cols == ["timestamp", "A+", "A-"]


def test_pivot_rows_are_sorted_unioned_timestamps() -> None:
    _, rows = pivot_readings(_two_block_payload())
    assert [r["timestamp"] for r in rows] == [
        "2026-06-01T00:15:00+02:00",
        "2026-06-01T00:30:00+02:00",
        "2026-06-01T00:45:00+02:00",
    ]


def test_pivot_fills_missing_cells_with_empty_string() -> None:
    _, rows = pivot_readings(_two_block_payload())
    assert rows[0] == {"timestamp": "2026-06-01T00:15:00+02:00", "A+": "0.5", "A-": "0.1"}
    assert rows[1] == {"timestamp": "2026-06-01T00:30:00+02:00", "A+": "0.7", "A-": ""}
    assert rows[2] == {"timestamp": "2026-06-01T00:45:00+02:00", "A+": "", "A-": "0.2"}


def test_pivot_unknown_code_falls_back_to_raw() -> None:
    payload = {
        "intervalBlocks": [
            {
                "readingType": "99.99.unknown",
                "intervalReadings": [{"timestamp": "2026-06-01T00:00:00Z", "value": "1"}],
            }
        ]
    }
    cols, _ = pivot_readings(payload)
    assert cols == ["timestamp", "99.99.unknown"]


def test_dump_readings_json_returns_pivoted_rows() -> None:
    out = dump_readings(_two_block_payload(), OutputFormat.JSON)
    rows = json.loads(out)
    assert isinstance(rows, list)
    assert rows[0]["A+"] == "0.5"


def test_dump_readings_table_contains_oznake_and_values() -> None:
    out = dump_readings(_two_block_payload(), OutputFormat.TABLE)
    assert "A+" in out
    assert "A-" in out
    assert "0.5" in out
    assert "0.7" in out


def test_dump_readings_empty_payload_renders_safely() -> None:
    out = dump_readings({"intervalBlocks": []}, OutputFormat.TABLE)
    assert "timestamp" in out
