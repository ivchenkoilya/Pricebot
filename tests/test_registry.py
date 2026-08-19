from app.trackers.generic import GenericProvider
from app.trackers.providers.ozon import OzonProvider
from app.trackers.registry import ProviderRegistry


def test_ozon_provider_has_priority(db):
    _database, settings = db
    registry = ProviderRegistry(settings)
    assert isinstance(registry.providers[0], OzonProvider)
    assert isinstance(registry.providers[-1], GenericProvider)
