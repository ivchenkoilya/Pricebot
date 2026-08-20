from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single env-backed configuration for Clarify plus legacy PRICE modules."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        validate_default=True,
    )

    # Core
    app_name: str = 'Clarify'
    version: str = '0.6.1'
    bot_token: str = ''
    admin_telegram_id: int | None = None
    test_mode: bool = True
    database_url: str = ''
    data_dir: str = ''
    port: int = 8080
    serve_http: bool = True
    default_timezone: str = 'Europe/Moscow'

    # Telegram Mini App
    webapp_url: str = ''
    webapp_auth_max_age_seconds: int = 86_400
    webapp_dev_auth: bool = False
    webapp_cors_origins: str = ''

    # Clarify AI
    ai_enabled: bool = True
    openai_api_key: str = ''
    openai_base_url: str = ''
    openai_model: str = 'gpt-5-mini'
    fast_model: str = ''
    smart_model: str = ''
    vision_model: str = ''
    openai_timeout: float = 60.0
    openai_max_output_tokens: int = 1400
    fast_text_chars: int = 12_000
    chunk_parallelism: int = 4
    retrieval_chunk_limit: int = 5
    recent_material_hours: int = 12
    image_max_side: int = 1600
    image_jpeg_quality: int = 82

    # Clarify FREE / PRO
    pro_stars_price: int = 299
    free_daily_ai_limit: int = 10
    pro_daily_ai_limit: int = 150
    free_voice_daily_limit: int = 3
    free_voice_max_seconds: int = 120
    free_document_max_pages: int = 10
    pro_document_max_pages: int = 200
    max_file_size_mb: int = 25

    # Speech-to-text
    stt_provider: str = 'local'
    whisper_model: str = 'base'
    stt_remote_model: str = 'whisper-1'
    stt_remote_timeout: float = 25.0
    whisper_compute_type: str = 'int8'
    whisper_cache_dir: str = ''

    # Concurrency / privacy
    max_ai_concurrency: int = 4
    max_stt_concurrency: int = 1
    max_document_concurrency: int = 2
    max_active_jobs_per_user: int = 2
    requests_per_minute: int = 30
    material_ttl_days: int = 30
    max_material_chars: int = 400_000

    # Legacy PRICE configuration kept intentionally so old modules/tests remain import-compatible.
    check_interval_free_hours: int = 24
    check_interval_pro_hours: int = 4
    free_product_limit: int = 3
    pro_product_limit: int = 50
    price_drop_threshold_percent: float = 1.0
    alert_cooldown_hours: int = 8
    request_timeout: float = 20.0
    max_retries: int = 2
    user_agent: str = 'Mozilla/5.0 (compatible; ClarifyBot/0.6; +https://t.me/)'

    @field_validator('stt_provider')
    @classmethod
    def validate_stt_provider(cls, value: str) -> str:
        clean = (value or 'local').strip().lower()
        if clean not in {'local', 'remote'}:
            raise ValueError('STT_PROVIDER must be local or remote')
        return clean

    @property
    def ai_available(self) -> bool:
        return bool(self.ai_enabled and self.openai_api_key and self.openai_model)

    @property
    def fast(self) -> str:
        return self.fast_model.strip() or self.openai_model

    @property
    def smart(self) -> str:
        return self.smart_model.strip() or self.openai_model

    @property
    def vision(self) -> str:
        return self.vision_model.strip() or self.smart

    @property
    def database_path(self) -> Path | None:
        prefix = 'sqlite+aiosqlite:///'
        if not self.database_url.startswith(prefix):
            return None
        return Path(self.database_url[len(prefix):])

    @property
    def data_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        if Path('/data').exists():
            return Path('/data')
        return Path('./data')

    @property
    def temp_dir(self) -> Path:
        return self.data_path / 'tmp'

    @property
    def whisper_cache_path(self) -> Path:
        if self.whisper_cache_dir:
            return Path(self.whisper_cache_dir)
        return self.data_path / 'whisper-cache'

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip().rstrip('/') for item in self.webapp_cors_origins.split(',') if item.strip()]

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.whisper_cache_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if not settings.database_url:
        if Path('/data').exists():
            settings.database_url = 'sqlite+aiosqlite:////data/price.db'
        else:
            settings.database_url = 'sqlite+aiosqlite:///./data/price.db'
    return settings
