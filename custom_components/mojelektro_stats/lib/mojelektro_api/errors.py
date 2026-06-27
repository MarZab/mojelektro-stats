from __future__ import annotations


class MojElektroError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_url: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_url = request_url
        self.response_body = response_body

    def __repr__(self) -> str:
        if self.status_code is None:
            return f"{type(self).__name__}({self.args[0]!r})"
        return f"{type(self).__name__}({self.args[0]!r}, status_code={self.status_code})"


class AuthError(MojElektroError):
    pass


class NotFoundError(MojElektroError):
    pass


class InvalidRequestError(MojElektroError):
    pass


class TransportError(MojElektroError):
    def __init__(
        self,
        message: str,
        *,
        original: BaseException | None = None,
        request_url: str | None = None,
    ) -> None:
        super().__init__(message, request_url=request_url)
        self.original = original
