from __future__ import annotations

from datetime import datetime, timedelta


VISUAL_QUERY_MARKERS = (
    'маск', 'человек', 'люди', 'одеж', 'кофт', 'футбол', 'куртк', 'штан', 'обув',
    'цвет', 'фон', 'предмет', 'в руках', 'на голове', 'на лице', 'что надет',
    'как выглядит', 'на фото', 'на фотке', 'на фотографии', 'на картинке',
    'на изображении', 'на скрине', 'на скриншоте', 'кто это', 'что это',
    'где он', 'где она', 'где они', 'что у него', 'что у неё', 'что у нее',
    'слева', 'справа', 'сзади', 'впереди', 'рядом', 'сидит', 'стоит',
)


def is_visual_followup(text: str) -> bool:
    low = ' '.join((text or '').lower().split())
    return bool(low and any(marker in low for marker in VISUAL_QUERY_MARKERS))


def _is_recent(item, recent_hours: int, now: datetime) -> bool:
    created_at = getattr(item, 'created_at', None)
    if created_at is None:
        return False
    return now - created_at <= timedelta(hours=recent_hours)


def select_recent_image(items, query: str, recent_hours: int, now: datetime | None = None):
    """Pick the image that a visual follow-up most likely refers to.

    Normally only the latest material is used. One recovery exception exists for
    an old Clarify bug: a short visual question itself could have been saved as a
    text material. In that case we skip that accidental text and recover the
    immediately preceding image.
    """
    if not items or not is_visual_followup(query):
        return None

    now = now or datetime.utcnow()
    recent = [item for item in items if _is_recent(item, recent_hours, now)]
    if not recent:
        return None

    latest = recent[0]
    if getattr(latest, 'type', '') == 'image':
        return latest

    latest_text = (getattr(latest, 'extracted_text', '') or '').strip()
    looks_like_accidental_followup = (
        getattr(latest, 'type', '') == 'text'
        and len(latest_text) <= 220
        and is_visual_followup(latest_text)
    )
    if looks_like_accidental_followup:
        for item in recent[1:4]:
            if getattr(item, 'type', '') == 'image':
                return item

    return None
