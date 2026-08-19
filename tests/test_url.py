import pytest

from app.utils import url as url_utils


def test_normalize_url_removes_tracking_but_keeps_product_params():
    value = url_utils.normalize_url('HTTPS://Example.COM/product?id=42&utm_source=tg&color=black#reviews')
    assert value == 'https://example.com/product?id=42&color=black'


def test_normalize_rejects_non_http():
    with pytest.raises(ValueError):
        url_utils.normalize_url('file:///etc/passwd')


@pytest.mark.asyncio
async def test_ssrf_blocks_localhost():
    with pytest.raises(ValueError):
        await url_utils.ensure_safe_url('http://127.0.0.1/secret')


@pytest.mark.asyncio
async def test_ssrf_blocks_dns_to_private(monkeypatch):
    async def fake_resolve(_host):
        return {'10.0.0.7'}
    monkeypatch.setattr(url_utils, 'resolve_host_ips', fake_resolve)
    with pytest.raises(ValueError):
        await url_utils.ensure_safe_url('https://shop.example/product')


@pytest.mark.asyncio
async def test_ssrf_accepts_public_dns(monkeypatch):
    async def fake_resolve(_host):
        return {'93.184.216.34'}
    monkeypatch.setattr(url_utils, 'resolve_host_ips', fake_resolve)
    assert await url_utils.ensure_safe_url('https://example.com/a?utm_source=x&id=1') == 'https://example.com/a?id=1'
