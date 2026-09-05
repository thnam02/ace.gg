from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

_EXEMPT_PATHS = frozenset({"/health", "/ops/vct-sync"})
_WINDOW_SECONDS = 60.0


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._windows: dict[str, deque[float]] = {}

    def hit(
        self, key: str, limit: int, window_seconds: float = _WINDOW_SECONDS
    ) -> tuple[bool, int]:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = self._windows.get(key)
            if hits is None:
                hits = deque()
                self._windows[key] = hits
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(hits[0] + window_seconds - now) + 1)
                return False, retry_after
            hits.append(now)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._windows.clear()


limiter = SlidingWindowLimiter()


def reset_rate_limiter() -> None:
    limiter.clear()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _limit_for_path(path: str) -> tuple[str, int]:
    if path.startswith("/players/compare"):
        return "compare", settings.rate_limit_compare_per_minute
    return "all", settings.rate_limit_per_minute


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        bucket, limit = _limit_for_path(path)
        allowed, retry_after = limiter.hit(f"{client_ip(request)}:{bucket}", limit)
        if not allowed:
            response: Response = JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
