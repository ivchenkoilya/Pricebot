from __future__ import annotations

from app.config.settings import Settings
from app.trackers.base import PriceProvider, ProductSnapshot, ProviderError
from app.trackers.generic import GenericProvider


class ProviderRegistry:
    def __init__(self, settings: Settings, providers: list[PriceProvider] | None = None):
        self.settings = settings
        self.providers = providers or [GenericProvider(settings)]

    async def fetch(self, url: str) -> ProductSnapshot:
        errors: list[str] = []
        for provider in self.providers:
            if provider.name.lower() in self.settings.disabled_provider_set:
                continue
            if await provider.supports(url):
                try:
                    return await provider.fetch(url)
                except ProviderError as exc:
                    errors.append(f'{provider.name}: {exc}')
        raise ProviderError('; '.join(errors) if errors else 'Нет подходящего provider')
