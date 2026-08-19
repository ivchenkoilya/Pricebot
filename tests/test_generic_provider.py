from decimal import Decimal

import pytest

from app.trackers.base import PriceNotFoundError
from app.trackers.generic import GenericProvider


def test_jsonld_product_parser():
    html = '''
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Sony WH-1000XM6","image":"https://img.example/x.jpg",
     "offers":{"@type":"Offer","price":"34990","priceCurrency":"RUB","availability":"https://schema.org/InStock"}}
    </script></head></html>
    '''
    snap = GenericProvider.parse_document(html, 'https://shop.example/sony')
    assert snap.product_name == 'Sony WH-1000XM6'
    assert snap.current_price == Decimal('34990.00')
    assert snap.currency == 'RUB'
    assert snap.availability == 'in_stock'
    assert snap.confidence >= 0.85


def test_low_confidence_html_requires_corroboration():
    html = '<html><head><title>Phone</title></head><body><div class="price">29 990 ₽</div></body></html>'
    with pytest.raises(PriceNotFoundError):
        GenericProvider.parse_document(html, 'https://shop.example/p')


def test_low_confidence_html_accepts_corroborated_price():
    html = '<html><head><title>Phone</title></head><body><div class="price">29 990 ₽</div><div class="current-price">29 990 ₽</div></body></html>'
    snap = GenericProvider.parse_document(html, 'https://shop.example/p')
    assert snap.current_price == Decimal('29990.00')
