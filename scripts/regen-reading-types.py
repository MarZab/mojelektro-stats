#!/usr/bin/env python3
"""Generate reading_types.py in the vendored lib from the /reading-type catalog.

Source: the response body of the recorded
`tests/lib/cassettes/test_client_recorded/test_recorded_reading_types.yaml`
cassette. The cassette scrub is path-aware: naziv stays intact for
reading-type items (Slovene description like "Prejeta 15 minutna delovna
energija") and is REDACTED only for merilno-mesto/lastnik responses.

Run: `make regen-reading-types`
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CASSETTE = (
    REPO_ROOT
    / "tests"
    / "lib"
    / "cassettes"
    / "test_client_recorded"
    / "test_recorded_reading_types.yaml"
)
TARGET = REPO_ROOT / "custom_components" / "mojelektro" / "lib" / "mojelektro" / "reading_types.py"

# Map raw catalog tokens → Python identifier fragments.
_OZNAKA_REPLACEMENTS = (
    ("+", "_PLUS"),
    ("-", "_MINUS"),
)
_PERIODA_MAP = {
    "15 min": "15MIN",
    "24 h": "DAILY",
}


def _slug(item: dict[str, str]) -> str:
    """Build a stable Python identifier from oznaka + perioda."""
    oznaka = item["oznaka"]
    perioda = item["perioda"]
    for src, dst in _OZNAKA_REPLACEMENTS:
        oznaka = oznaka.replace(src, dst)
    period_part = _PERIODA_MAP.get(perioda)
    if period_part is None:
        raise ValueError(f"unrecognized perioda {perioda!r} in {item!r}")
    raw = f"{oznaka}_{period_part}"
    # Collapse any remaining non-alphanumeric → underscore
    raw = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw or raw[0].isdigit():
        raw = "T_" + raw
    return raw.upper()


def _load_catalog() -> list[dict[str, str]]:
    cassette = yaml.safe_load(CASSETTE.read_text())
    body = cassette["interactions"][0]["response"]["body"]["string"]
    items: list[dict[str, str]] = json.loads(body)
    return items


def _render(items: list[dict[str, str]]) -> str:
    seen: dict[str, dict[str, str]] = {}
    for item in items:
        name = _slug(item)
        if name in seen:
            raise ValueError(f"duplicate slug {name!r} from {item!r} (also {seen[name]!r})")
        seen[name] = item

    lines: list[str] = [
        '"""Typed constants for the Moj Elektro reading-type catalog.',
        "",
        "GENERATED FILE. Do not edit by hand. Regenerate with:",
        "    make regen-reading-types",
        "",
        f"Source: {CASSETTE.relative_to(REPO_ROOT)}",
        f"Catalog size: {len(items)} reading types",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from enum import StrEnum",
        "",
        "",
        "class ReadingTypeCode(StrEnum):",
        '    """API option-parameter values, ready to pass into',
        "    `MojElektroClient.get_meter_readings(..., options=[...])`.",
        '    """',
        "",
    ]
    for name, item in seen.items():
        lines.append(f'    {name} = "ReadingType={item["readingType"]}"')

    lines += [
        "",
        "",
        "@dataclass(frozen=True, slots=True)",
        "class ReadingTypeInfo:",
        '    """Catalog metadata for a known reading type."""',
        "",
        "    name: str",
        "    oznaka: str",
        "    perioda: str",
        "    tip: str",
        "    vrsta: str",
        "    opis: str",
        "    code: ReadingTypeCode",
        '    naziv: str = ""  # API description; "" if cassette is pre-scrub-refactor',
        "",
        "",
        "KNOWN_READING_TYPES: tuple[ReadingTypeInfo, ...] = (",
    ]
    for name, item in seen.items():
        lines.append("    ReadingTypeInfo(")
        lines.append(f"        name={name!r},")
        lines.append(f"        oznaka={item['oznaka']!r},")
        lines.append(f"        perioda={item['perioda']!r},")
        lines.append(f"        tip={item['tip']!r},")
        lines.append(f"        vrsta={item['vrsta']!r},")
        lines.append(f"        opis={item['opis']!r},")
        lines.append(f"        code=ReadingTypeCode.{name},")
        if item.get("naziv"):
            lines.append(f"        naziv={item['naziv']!r},")
        lines.append("    ),")
    lines.append(")")

    lines += [
        "",
        "",
        "BY_NAME: dict[str, ReadingTypeInfo] = {rt.name: rt for rt in KNOWN_READING_TYPES}",
        "BY_OZNAKA: dict[str, tuple[ReadingTypeInfo, ...]] = {",
        "    oznaka: tuple(rt for rt in KNOWN_READING_TYPES if rt.oznaka == oznaka)",
        "    for oznaka in {rt.oznaka for rt in KNOWN_READING_TYPES}",
        "}",
        "# Keyed by the raw code (no `ReadingType=` prefix) — used to look up",
        "# catalog metadata for the readingType field returned in API responses.",
        "BY_RAW_CODE: dict[str, ReadingTypeInfo] = {",
        '    rt.code.value.removeprefix("ReadingType="): rt for rt in KNOWN_READING_TYPES',
        "}",
        "",
        '__all__ = ["BY_NAME", "BY_OZNAKA", "BY_RAW_CODE", "KNOWN_READING_TYPES", '
        '"ReadingTypeCode", "ReadingTypeInfo"]',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    items = _load_catalog()
    rendered = _render(items)
    TARGET.write_text(rendered)
    print(f"wrote {TARGET.relative_to(REPO_ROOT)} ({len(items)} reading types)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
