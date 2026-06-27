from __future__ import annotations

import httpx

from mojelektro.errors import (
    AuthError,
    InvalidRequestError,
    MojElektroError,
    NotFoundError,
)


def raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    message = _extract_message(response)
    body = response.text
    url = str(response.request.url) if response.request is not None else None
    kwargs: dict[str, object] = {
        "status_code": status,
        "request_url": url,
        "response_body": body,
    }
    if status in (401, 403):
        raise AuthError(message, **kwargs)  # type: ignore[arg-type]
    if status == 404:
        raise NotFoundError(message, **kwargs)  # type: ignore[arg-type]
    if status == 400:
        raise InvalidRequestError(message, **kwargs)  # type: ignore[arg-type]
    raise MojElektroError(message, **kwargs)  # type: ignore[arg-type]


def _extract_message(response: httpx.Response) -> str:
    fallback = f"HTTP {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        body = response.text.strip()
        return f"{fallback}: {_truncate(body)}" if body else fallback
    if isinstance(data, dict):
        for key in ("opisNapake", "message", "error", "title"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    # JSON, but no known field — surface the raw payload so callers can debug.
    return f"{fallback}: {_truncate(response.text)}"


def _truncate(text: str, limit: int = 500) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f"...[truncated, {len(text)} bytes]"
