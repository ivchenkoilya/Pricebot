from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore', validate_default=True)

    app_name: str = 'PRICE'
    version: str = '0.1.0'
    bot_token: str = ''
    admin_telegram_id: int | None = None
    test_mode: bool = True
    database_url: str = ''
    port: int = 8080
    serve_http: bool = True
    default_timezone: str = 'Europe/Moscow'

    check_interval_free_hours: int = 12
    check_interval_pro_hours: int = 2
    free_watch_limit: int = 3
    pro_watch_limit: int = 50
    pro_stars_price: int = 199
    request_timeout: float = 20.0
    max_provider_failures: int = 5
    provider_batch_size: int = 20
    scheduler_tick_seconds: int = 60
    min_drop_percent: float = 3.0
    alert_cooldown_hours: int = 6
    user_rate_limit_per_minute: int = 20
    global_fetch_concurrency: int = 8
    per_host_fetch_concurrency: int = 2
    min_host_request_interval_seconds: float = 1.0
    max_response_bytes: int = 2_000_000
    provider_user_agent: str = 'PRICE/0.1 (+Telegram price tracker; respectful fetcher)'
    disabled_providers: str = ''

    ai_enabled: bool = True
    openai_api_key: str = ''
    openai_model: str = 'gpt-5-mini'
    openai_timeout: float = 15.0
    openai_max_output_tokens: int = 300

    @field_validator('admin_telegram_id', mode='before')
    @classmethod
    def empty_admin_to_none(cls, value):
        if value in ('', None):
            return None
        return int(value)

    @field_validator('database_url', mode='before')
    @classmethod
    def default_database(cls, value):
        if value:
            return value
        data_path = Path('/data')
        if data_path.exists() and data_path.is_dir():
            return 'sqlite+aiosqlite:////data/price.db'
        Path('./data').mkdir(parents=True, exist_ok=True)
        return 'sqlite+aiosqlite:///./data/price.db'

    @property
    def disabled_provider_set(self) -> set[str]:
        return {item.strip().lower() for item in self.disabled_providers.split(',') if item.strip()}

    @property
    def ai_available(self) -> bool:
        return bool(self.ai_enabled and self.openai_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
