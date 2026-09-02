from __future__ import annotations

from app.providers.vlr_api_ingestion_provider import VlrApiIngestionProvider
from app.providers.vlrggapi_client import VlrggApiClient


def create_vlrggapi_client(
    base_url: str,
    *,
    timeout: float = 30.0,
    request_delay: float = 0.0,
    max_retries: int = 6,
) -> VlrggApiClient:
    return VlrggApiClient(
        base_url,
        timeout=timeout,
        request_delay=request_delay,
        max_retries=max_retries,
    )


def create_vlr_api_ingestion_provider(
    base_url: str,
    *,
    timeout: float = 30.0,
    client: VlrggApiClient | None = None,
) -> VlrApiIngestionProvider:
    api_client = client or create_vlrggapi_client(base_url, timeout=timeout)
    return VlrApiIngestionProvider(api_client)
