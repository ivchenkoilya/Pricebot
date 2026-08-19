from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
    'gclid', 'fbclid', 'yclid', '_openstat', 'mc_cid', 'mc_eid', 'referrer',
}


def normalize_url(url: str) -> str:
    value = url.strip()
    parts = urlsplit(value)
    if parts.scheme.lower() not in {'http', 'https'} or not parts.hostname:
        raise ValueError('Нужна корректная http/https ссылка')
    scheme = parts.scheme.lower()
    host = parts.hostname.lower().rstrip('.')
    port = parts.port
    netloc = host
    if port and not ((scheme == 'http' and port == 80) or (scheme == 'https' and port == 443)):
        netloc = f'{host}:{port}'
    clean_query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    query = urlencode(clean_query, doseq=True)
    path = parts.path or '/'
    return urlunsplit((scheme, netloc, path, query, ''))


def is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any((
        addr.is_private,
        addr.is_loopback,
        addr.is_link_local,
        addr.is_multicast,
        addr.is_reserved,
        addr.is_unspecified,
    ))


async def resolve_host_ips(host: str) -> set[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    return {info[4][0] for info in infos}


async def ensure_safe_url(url: str) -> str:
    normalized = normalize_url(url)
    parts = urlsplit(normalized)
    host = parts.hostname or ''
    if host in {'localhost', 'localhost.localdomain'}:
        raise ValueError('Внутренние адреса запрещены')
    try:
        if is_blocked_ip(host):
            raise ValueError('Внутренние адреса запрещены')
    except ValueError as exc:
        if 'does not appear' not in str(exc):
            raise
    ips = await resolve_host_ips(host)
    if not ips or any(is_blocked_ip(ip) for ip in ips):
        raise ValueError('Адрес ведёт во внутреннюю или служебную сеть')
    return normalized


def redirect_url(base: str, location: str) -> str:
    return urljoin(base, location)
