from datetime import datetime, timedelta
from types import SimpleNamespace

from app.ai.context import is_visual_followup, select_recent_image


def material(type_, text='', minutes_ago=0, file_id='file-id'):
    return SimpleNamespace(
        type=type_,
        extracted_text=text,
        telegram_file_id=file_id,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
    )


def test_visual_followup_detection_for_real_case():
    assert is_visual_followup('В какой маске этот человек') is True
    assert is_visual_followup('какого цвета у него одежда') is True
    assert is_visual_followup('как сделать сайт для магазина') is False


def test_latest_image_is_selected_for_visual_question():
    image = material('image', minutes_ago=1)
    selected = select_recent_image([image], 'В какой маске этот человек', recent_hours=12)
    assert selected is image


def test_recovers_image_after_old_accidental_followup_material():
    accidental = material('text', 'В какой маске этот человек', minutes_ago=1, file_id=None)
    image = material('image', minutes_ago=2)
    selected = select_recent_image(
        [accidental, image],
        'какого цвета маска',
        recent_hours=12,
    )
    assert selected is image


def test_does_not_jump_over_real_new_document():
    document = material('pdf', 'Договор поставки', minutes_ago=1, file_id='doc')
    image = material('image', minutes_ago=2)
    selected = select_recent_image(
        [document, image],
        'что у него в руках',
        recent_hours=12,
    )
    assert selected is None
