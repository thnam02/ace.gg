from __future__ import annotations


class VlrggApiError(Exception):
    """Base error for vlrggapi client failures."""


class VlrggApiHttpError(VlrggApiError):
    def __init__(self, status_code: int, path: str, message: str | None = None) -> None:
        self.status_code = status_code
        self.path = path
        super().__init__(message or f"vlrggapi HTTP {status_code} for {path}")


class VlrggApiMalformedResponseError(VlrggApiError):
    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        super().__init__(f"Malformed vlrggapi response for {path}: {detail}")


class VlrggApiStatusError(VlrggApiError):
    def __init__(self, path: str, status: str) -> None:
        self.path = path
        self.api_status = status
        super().__init__(f"vlrggapi returned status={status} for {path}")
