from io import BytesIO

from PIL import Image

from app.brand import clarify_banner_jpeg, clarify_banner_webp


def test_supplied_banner_is_valid_webp_and_jpeg():
    webp = clarify_banner_webp()
    assert webp[:4] == b'RIFF'
    with Image.open(BytesIO(webp)) as image:
        assert image.format == 'WEBP'
        assert image.size == (1024, 576)

    jpeg = clarify_banner_jpeg()
    assert jpeg[:2] == b'\xff\xd8'
    with Image.open(BytesIO(jpeg)) as image:
        assert image.format == 'JPEG'
        assert image.size == (1024, 576)
