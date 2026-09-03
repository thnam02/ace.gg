from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://valorant:valorant@localhost:5432/valorant_scout"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = r"https://.*\.vercel\.app"
    docs_enabled: bool = True
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 600
    rate_limit_compare_per_minute: int = 60
    data_provider: str = "mock"
    vlrggapi_base_url: str = "http://127.0.0.1:3001"
    vlr_circuit_url: str = "https://www.vlr.gg/vct"
    vct_sync_season_year: int = 2026
    vct_sync_cron: str = "0 3 * * *"
    vlr_default_players: str = "tenz,aspas,something"
    vlr_stats_region: str = "americas"
    vlr_stats_timespan: str = "90"
    vlr_player_timespan: str = "90d"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cors_origin_regex_value(self) -> str | None:
        value = self.cors_origin_regex.strip()
        return value or None

    @property
    def vlr_default_player_list(self) -> list[str]:
        return [player.strip() for player in self.vlr_default_players.split(",") if player.strip()]


settings = Settings()
