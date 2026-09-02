from app.config import settings
from app.providers.base import PlayerDataProvider
from app.providers.mock import MockPlayerDataProvider
from app.providers.vlr import VlrPlayerDataProvider
from app.providers.vlrggapi_factory import create_vlrggapi_client


def create_player_data_provider() -> PlayerDataProvider:
    if settings.data_provider == "vlr":
        client = create_vlrggapi_client(settings.vlrggapi_base_url)
        return VlrPlayerDataProvider(
            settings.vlrggapi_base_url,
            default_players=settings.vlr_default_player_list,
            stats_region=settings.vlr_stats_region,
            stats_timespan=settings.vlr_stats_timespan,
            player_timespan=settings.vlr_player_timespan,
            client=client,
        )
    return MockPlayerDataProvider()
