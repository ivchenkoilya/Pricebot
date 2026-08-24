from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image


_DATA_DIR = Path(__file__).resolve().parent / 'banner_data'


@lru_cache(maxsize=1)
def clarify_banner_webp() -> bytes:
    """Return the current Clarify product banner.

    The binary is stored as small base64 text chunks so it can be updated safely
    through the repository content API. Mini App serves the WebP directly;
    Telegram /start gets a JPEG conversion for maximum client compatibility.
    """
    encoded = ''.join(
        (_DATA_DIR / f'part{index}.txt').read_text(encoding='ascii').strip()
        for index in range(1, 8)
    )
    return base64.b64decode(encoded, validate=True)


@lru_cache(maxsize=1)
def clarify_banner_jpeg() -> bytes:
    with Image.open(BytesIO(clarify_banner_webp())) as image:
        image.load()
        if image.mode != 'RGB':
            image = image.convert('RGB')
        output = BytesIO()
        image.save(output, format='JPEG', quality=92, optimize=True, progressive=True)
        return output.getvalue()
