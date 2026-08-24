import pytest

from app.utils import url as url_utils


def test_normalize_url_removes_tracking_but_keeps_product_params():
    value = url_utils.normalize_url('HTTPS://Example.COM/product?id=42&utm_source=tg&color=black#reviews')
    assert value == 'https://example.com/product?id=42&color=black'


def test_normalize_url_adds_https_to_plain_domain():
    assert url_utils.normalize_url('vk.ru') == 'https://vk.ru/'
    assert url_utils.normalize_url('www.example.com/path?q=1') == 'https://www.example.com/path?q=1'


def test_find_urls_supports_plain_domains_without_matching_email():
    text = 'Смотри vk.ru и https://example.com/a. Почта user@example.com не ссылка.'
    assert url_utils.find_urls(text) == ['https://vk.ru/', 'https://example.com/a']


def test_strip_urls_removes_http_and_plain_domain_tokens():
    assert url_utils.strip_urls('разбери vk.ru пожалуйста') == 'разбери пожалуйста'


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
