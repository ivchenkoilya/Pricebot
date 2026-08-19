from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductSnapshot(BaseModel):
    product_name: str
    current_price: Decimal | None = None
    old_price: Decimal | None = None
    currency: str | None = None
    availability: str = 'unknown'
    image_url: str | None = None
    canonical_url: str
    seller: str | None = None
    source: str
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 0.0


class PriceProvider(ABC):
    name = 'base'

    @abstractmethod
    async def supports(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, url: str) -> ProductSnapshot:
        raise NotImplementedError


class ProviderError(RuntimeError):
    pass


class PriceNotFoundError(ProviderError):
    pass


class SourceBlockedError(ProviderError):
    pass
