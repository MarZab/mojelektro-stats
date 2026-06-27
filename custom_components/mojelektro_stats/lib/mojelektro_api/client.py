from __future__ import annotations

from datetime import date
from types import TracebackType
from typing import Any, Self

import httpx

from mojelektro_api._http import raise_for_status
from mojelektro_api.errors import TransportError
from mojelektro_api.models import MerilnaTocka, MerilnoMesto, MeterReadings, Server

_TRANSIENT = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)

_TOKEN_HEADER = "X-API-TOKEN"


class MojElektroClient:
    def __init__(
        self,
        api_token: str,
        *,
        server: Server = Server.PRODUCTION,
        http: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = api_token
        self._server = server
        self._timeout = timeout
        self._owns_http = http is None
        if http is None:
            self._http: httpx.AsyncClient = httpx.AsyncClient(
                base_url=server.base_url,
                headers={_TOKEN_HEADER: api_token, "Accept": "application/json"},
                timeout=timeout,
            )
        else:
            self._http = http
            self._http.headers[_TOKEN_HEADER] = api_token

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, url, **kwargs)
        except _TRANSIENT as exc:
            full_url = str(self._http.build_request(method, url, **kwargs).url)
            raise TransportError(
                str(exc) or type(exc).__name__,
                original=exc,
                request_url=full_url,
            ) from exc
        raise_for_status(response)
        return response

    async def get_merilno_mesto(self, identifikator: str) -> MerilnoMesto:
        response = await self._request("GET", f"/merilno-mesto/{identifikator}")
        payload: MerilnoMesto = response.json()
        return payload

    async def get_merilna_tocka(self, gsrn: str) -> MerilnaTocka:
        response = await self._request("GET", f"/merilna-tocka/{gsrn}")
        payload: MerilnaTocka = response.json()
        return payload

    async def get_meter_readings(
        self,
        usage_point: str,
        start: date,
        end: date,
        *,
        options: list[str] | None = None,
    ) -> MeterReadings:
        params: dict[str, str | list[str]] = {
            "usagePoint": usage_point,
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        }
        if options:
            params["option"] = list(options)
        response = await self._request("GET", "/meter-readings", params=params)
        payload: MeterReadings = response.json()
        return payload
