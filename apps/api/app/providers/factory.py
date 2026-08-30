from app.config import settings
from app.providers.base import PlayerDataProvider
from app.providers.mock import MockPlayerDataProvider
from app.providers.vlr import VlrPlayerDataProvider


def create_player_data_provider() -> PlayerDataProvider:
    if settings.data_provider == "vlr":
        return VlrPlayerDataProvider(
            base_url=settings.vlrggapi_base_url,
            default_players=settings.vlr_default_player_list,
            stats_region=settings.vlr_stats_region,
            stats_timespan=settings.vlr_stats_timespan,
            player_timespan=settings.vlr_player_timespan,
        )
    return MockPlayerDataProvider()
