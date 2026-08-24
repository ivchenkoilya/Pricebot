from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image


_BANNER_PATH = Path(__file__).resolve().parent / 'banner_data' / 'clarify_banner.webp'


@lru_cache(maxsize=1)
def clarify_banner_webp() -> bytes:
    """Return the current Clarify product banner.

    Mini App serves this WebP directly; Telegram /start gets a JPEG conversion
    for maximum client compatibility.
    """
    return _BANNER_PATH.read_bytes()


@lru_cache(maxsize=1)
def clarify_banner_jpeg() -> bytes:
    with Image.open(BytesIO(clarify_banner_webp())) as image:
        image.load()
        if image.mode != 'RGB':
            image = image.convert('RGB')
        output = BytesIO()
        image.save(output, format='JPEG', quality=92, optimize=True, progressive=True)
        return output.getvalue()
