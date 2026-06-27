"""Identifier resolution helpers shared by the readings + meter commands.

The Moj Elektro API uses three distinct identifiers per measuring point
(identifikator / gsrnMm / gsrnMt — see the api-identifier-model memory).
These helpers let CLI commands accept the short identifikator that users
actually know and look up the long-form GSRN they need.

If the input is already an 18-digit number we treat it as the GSRN being
asked for and return it as-is (no API call).
"""

from __future__ import annotations

import re

import typer

from mojelektro import MojElektroClient
from mojelektro.models import MerilnoMesto

_GSRN_RE = re.compile(r"^\d{18}$")


async def _fetch_merilno_mesto(client: MojElektroClient, identifier: str) -> MerilnoMesto:
    return await client.get_merilno_mesto(identifier)


def _pluck(payload: object, *path: str) -> object | None:
    """Walk a nested dict by string keys; return None at the first miss."""
    cur: object = payload
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


async def resolve_gsrn_mm(client: MojElektroClient, identifier: str) -> str:
    """Return the meter GSRN (gsrnMm) for `/meter-readings?usagePoint=…`.

    18-digit input passes through. Otherwise looked up via /merilno-mesto.
    """
    if _GSRN_RE.match(identifier):
        return identifier
    payload = await _fetch_merilno_mesto(client, identifier)
    gsrn = _pluck(payload, "identifikator", "gsrn")
    if not isinstance(gsrn, str) or not gsrn:
        raise typer.BadParameter(
            f"could not resolve identifikator {identifier!r} to a meter GSRN (gsrnMm)",
            param_hint="USAGE_POINT",
        )
    return gsrn


async def resolve_gsrn_mt(client: MojElektroClient, identifier: str) -> str:
    """Return the contract GSRN (gsrnMt) for `/merilna-tocka/{gsrnMt}`.

    18-digit input passes through. Otherwise looked up via /merilno-mesto;
    the first associated merilna tocka is used.
    """
    if _GSRN_RE.match(identifier):
        return identifier
    payload = await _fetch_merilno_mesto(client, identifier)
    points = _pluck(payload, "merilneTocke")
    if not isinstance(points, list) or not points:
        raise typer.BadParameter(
            f"merilno mesto {identifier!r} has no associated merilne tocke",
            param_hint="GSRN",
        )
    first = points[0]
    gsrn = first.get("gsrn") if isinstance(first, dict) else None
    if not isinstance(gsrn, str) or not gsrn:
        raise typer.BadParameter(
            f"could not resolve identifikator {identifier!r} to a contract GSRN (gsrnMt)",
            param_hint="GSRN",
        )
    return gsrn
