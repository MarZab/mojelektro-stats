from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

import yaml

from mojelektro.reading_types import BY_RAW_CODE


class OutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"
    YAML = "yaml"


# Two-space gutter between columns. Wide enough to scan, tight enough to
# stay parsable by `awk '{print $1, $2}'` style pipelines.
_COL_GUTTER = "  "


def dump(payload: Any, fmt: OutputFormat) -> str:
    if fmt is OutputFormat.JSON:
        return json.dumps(payload, indent=2, sort_keys=True, default=str)
    if fmt is OutputFormat.YAML:
        return yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)
    if isinstance(payload, dict):
        # Flatten to dot-path leaf rows so nested objects/arrays don't end up
        # as `{'k': 'v', …}` blobs in a single cell.
        pairs = flatten_to_pairs(payload)
        string_rows = [[k, v] for k, v in pairs]
        return _render_columns(["key", "value"], string_rows)
    if isinstance(payload, list):
        rows = [item if isinstance(item, dict) else {"value": item} for item in payload]
    else:
        rows = [{"value": payload}]
    if not rows:
        return ""
    columns = list(rows[0].keys())
    string_rows = [[str(row.get(col, "")) for col in columns] for row in rows]
    return _render_columns(columns, string_rows)


def flatten_to_pairs(payload: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Walk a JSON-like value into (dot-path, stringified-leaf) pairs.

    - Dict children extend the path as `parent.child`.
    - List children extend the path as `parent.<index>` (zero-based).
    - Empty containers are emitted as a single row with value `{}` or `[]`.
    - None becomes an empty string; everything else is `str()`-coerced.
    """
    if isinstance(payload, dict):
        if not payload:
            return [(prefix, "{}")]
        pairs: list[tuple[str, str]] = []
        for k, v in payload.items():
            child_prefix = f"{prefix}.{k}" if prefix else str(k)
            pairs.extend(flatten_to_pairs(v, child_prefix))
        return pairs
    if isinstance(payload, list):
        if not payload:
            return [(prefix, "[]")]
        pairs = []
        for i, v in enumerate(payload):
            child_prefix = f"{prefix}.{i}" if prefix else str(i)
            pairs.extend(flatten_to_pairs(v, child_prefix))
        return pairs
    return [(prefix, "" if payload is None else str(payload))]


def _render_columns(columns: list[str], rows: list[list[str]]) -> str:
    """Render an aligned column-text table — no box drawing, no truncation."""
    header_lines, data_lines = render_aligned_lines(columns, rows)
    return "\n".join([*header_lines, *data_lines]) + "\n"


def render_aligned_lines(columns: list[str], rows: list[list[str]]) -> tuple[list[str], list[str]]:
    """Return (header_lines, data_lines) — same layout as `_render_columns`,
    but split so the pager can print the header once and stream the rows.
    """
    widths = compute_widths(columns, rows)
    header = [
        format_row(columns, widths),
        format_row(["-" * w for w in widths], widths),
    ]
    data = [format_row(row, widths) for row in rows]
    return header, data


def compute_widths(columns: list[str], rows: list[list[str]]) -> list[int]:
    """Per-column max width across header + rows."""
    widths = [len(col) for col in columns]
    for row in rows:
        for i, cell in enumerate(row):
            if len(cell) > widths[i]:
                widths[i] = len(cell)
    return widths


def format_row(cells: list[str], widths: list[int]) -> str:
    """Format one row with the supplied column widths. Right-edge trimmed."""
    parts = [cell.ljust(width) for cell, width in zip(cells, widths, strict=True)]
    return _COL_GUTTER.join(parts).rstrip()


def pivot_readings(meter_readings: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    """Pivot a /meter-readings response into (column_names, rows).

    - Columns: one per requested reading type, labelled by `oznaka` when the
      code is in the known catalog, otherwise the raw code is used.
    - Rows: one per distinct timestamp across all blocks, sorted ascending.
    - Empty cells are rendered as "" (not "None").
    """
    blocks = meter_readings.get("intervalBlocks") or []
    columns: list[str] = []
    by_ts: dict[str, dict[str, str]] = {}
    for block in blocks:
        raw_code = block.get("readingType") or ""
        info = BY_RAW_CODE.get(raw_code)
        label = info.oznaka if info else raw_code
        # Disambiguate duplicate labels (e.g. when two blocks have the same
        # oznaka but different periodicity) by appending the period.
        if label in columns and info is not None:
            label = f"{info.oznaka}/{info.perioda}"
        if label not in columns:
            columns.append(label)
        for reading in block.get("intervalReadings") or []:
            ts = str(reading.get("timestamp", ""))
            by_ts.setdefault(ts, {})[label] = str(reading.get("value", ""))

    rows = [
        {"timestamp": ts, **{col: by_ts[ts].get(col, "") for col in columns}}
        for ts in sorted(by_ts)
    ]
    return ["timestamp", *columns], rows


def dump_readings(meter_readings: dict[str, Any], fmt: OutputFormat) -> str:
    """Format a /meter-readings response.

    `table` produces a pivot (timestamp rows by reading-type columns).
    `json` / `yaml` return the pivoted rows so machine consumers also get
    the condensed shape instead of the raw nested intervalBlocks.
    """
    columns, rows = pivot_readings(meter_readings)
    if fmt is OutputFormat.JSON:
        return json.dumps(rows, indent=2, default=str)
    if fmt is OutputFormat.YAML:
        return yaml.safe_dump(rows, sort_keys=False, allow_unicode=True)
    string_rows = [[row.get(col, "") for col in columns] for row in rows]
    return _render_columns(columns, string_rows)
