from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
    'gclid', 'fbclid', 'yclid', '_openstat', 'mc_cid', 'mc_eid', 'referrer',
}

# Conservative public-domain matcher used for chat input. It intentionally does
# not match e-mail addresses and requires a real dot + 2+ character TLD, so a
# random sentence fragment such as "версия.новая" is much less likely to be
# treated as a URL. HTTP(S) links remain accepted as before.
URL_CANDIDATE_RE = re.compile(
    r'(?<![@\w])('
    r'(?:https?://[^\s<>"\']+)'
    r'|(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
    r'(?:xn--[a-z0-9-]{2,59}|[a-z]{2,63})'
    r'(?::\d{1,5})?(?:[/?#][^\s<>"\']*)?'
    r')',
    flags=re.IGNORECASE,
)

_TRAILING_URL_PUNCTUATION = '.,;:!?)]}»”’'


def _with_default_scheme(value: str) -> str:
    clean = (value or '').strip()
    if not clean:
        return clean
    if re.match(r'^https?://', clean, flags=re.IGNORECASE):
        return clean
    return 'https://' + clean


def normalize_url(url: str) -> str:
    value = _with_default_scheme(url)
    parts = urlsplit(value)
    if parts.scheme.lower() not in {'http', 'https'} or not parts.hostname:
        raise ValueError('Нужна корректная http/https ссылка')
    scheme = parts.scheme.lower()
    host = parts.hostname.lower().rstrip('.')
    if '.' not in host and host not in {'localhost', 'localhost.localdomain'}:
        raise ValueError('Нужна корректная ссылка с доменом')
    port = parts.port
    netloc = host
    if port and not ((scheme == 'http' and port == 80) or (scheme == 'https' and port == 443)):
        netloc = f'{host}:{port}'
    clean_query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    query = urlencode(clean_query, doseq=True)
    path = parts.path or '/'
    return urlunsplit((scheme, netloc, path, query, ''))


def find_urls(text: str, limit: int = 3) -> list[str]:
    """Extract HTTP(S) or ordinary schemeless public domains from chat text."""
    urls: list[str] = []
    for match in URL_CANDIDATE_RE.finditer(text or ''):
        raw = match.group(1).rstrip(_TRAILING_URL_PUNCTUATION)
        try:
            normalized = normalize_url(raw)
        except (TypeError, ValueError):
            continue
        if normalized not in urls:
            urls.append(normalized)
        if len(urls) >= max(1, int(limit)):
            break
    return urls


def strip_urls(text: str) -> str:
    """Remove URL-looking tokens while preserving the surrounding user text."""
    value = URL_CANDIDATE_RE.sub(' ', text or '')
    return re.sub(r'\s+', ' ', value).strip(' \n\t-—:')


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
