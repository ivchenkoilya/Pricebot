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
    version: str = '0.9.0'
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

    # Public media links: YouTube / Shorts / TikTok (+ best-effort Instagram/X)
    media_download_enabled: bool = True
    media_max_file_mb: int = 100
    media_free_max_file_mb: int = 50
    media_max_duration_minutes: int = 60
    media_free_max_duration_minutes: int = 10
    media_video_max_height: int = 720
    media_temp_dir: str = ''
    media_action_timeout_seconds: int = 27
    media_inspect_timeout_seconds: int = 8
    media_subtitle_timeout_seconds: int = 5
    media_fast_subtitles: bool = True
    media_metadata_cache_seconds: int = 900
    media_whisper_model: str = 'tiny'
    # Optional rotating HTTP(S) proxy. Recommended when YouTube blocks the
    # datacenter IP of Amvera. Example: http://user:pass@proxy.example:8080
    media_proxy_url: str = ''

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

    # Legacy PRICE settings retained so old modules/tests stay import-compatible.
    check_interval_free_hours: int = 12
    check_interval_pro_hours: int = 2
    free_watch_limit: int = 3
    pro_watch_limit: int = 50
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
    page_reader_jina_enabled: bool = True
    jina_reader_api_key: str = ''
    page_reader_timeout: float = 25.0
    page_reader_min_chars: int = 120
    page_reader_max_chars: int = 24_000

    @field_validator('admin_telegram_id', mode='before')
    @classmethod
    def empty_admin_to_none(cls, value):
        if value in ('', None, 0, '0'):
            return None
        return int(value)

    @field_validator('webapp_url', mode='before')
    @classmethod
    def normalize_amvera_webapp_url(cls, value):
        if not value:
            return value
        url = str(value).strip()
        url = url.replace('https://pricebot2.ivch.amvera.io', 'https://pricebot2-ivch.amvera.io')
        url = url.replace('http://pricebot2.ivch.amvera.io', 'https://pricebot2-ivch.amvera.io')
        return url

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

    @field_validator('data_dir', mode='before')
    @classmethod
    def default_data_dir(cls, value):
        if value:
            return str(value)
        data_path = Path('/data')
        if data_path.exists() and data_path.is_dir():
            return '/data'
        return './data'

    @property
    def fast(self) -> str:
        return self.fast_model.strip() or self.openai_model.strip()

    @property
    def smart(self) -> str:
        return self.smart_model.strip() or self.openai_model.strip()

    @property
    def vision(self) -> str:
        return self.vision_model.strip() or self.smart_model.strip() or self.openai_model.strip()

    @property
    def disabled_provider_set(self) -> set[str]:
        return {item.strip().lower() for item in self.disabled_providers.split(',') if item.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip().rstrip('/') for item in self.webapp_cors_origins.split(',') if item.strip()]

    @property
    def ai_available(self) -> bool:
        return bool(self.ai_enabled and self.openai_api_key.strip() and self.openai_model.strip())

    @property
    def ai_uses_custom_endpoint(self) -> bool:
        return bool(self.openai_base_url.strip())

    @property
    def resolved_media_temp_dir(self) -> str:
        return self.media_temp_dir or str(Path(self.data_dir) / 'tmp' / 'media')

    def ensure_dirs(self) -> None:
        base = Path(self.data_dir)
        base.mkdir(parents=True, exist_ok=True)
        (base / 'tmp').mkdir(parents=True, exist_ok=True)
        Path(self.resolved_whisper_cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.resolved_media_temp_dir).mkdir(parents=True, exist_ok=True)

    @property
    def resolved_whisper_cache_dir(self) -> str:
        return self.whisper_cache_dir or str(Path(self.data_dir) / 'whisper-cache')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
