from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _font(size: int, bold: bool = False):
    names = ['DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf', 'Arial.ttf']
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=1)
def clarify_banner_jpeg() -> bytes:
    """Generate a valid Telegram/browser banner without relying on binary repo assets."""
    width, height = 1400, 700
    image = Image.new('RGB', (width, height), '#061226')
    draw = ImageDraw.Draw(image)

    top = (7, 20, 46)
    bottom = (11, 16, 38)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, width, y), fill=color)

    glow = Image.new('RGBA', image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((780, -180, 1540, 580), fill=(38, 136, 255, 105))
    gd.ellipse((-220, 260, 620, 1030), fill=(128, 72, 255, 90))
    gd.ellipse((420, 80, 1100, 760), fill=(0, 209, 255, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    image = Image.alpha_composite(image.convert('RGBA'), glow)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((72, 70, 245, 243), radius=48, fill=(27, 148, 255, 255))
    badge_glow = Image.new('RGBA', image.size, (0, 0, 0, 0))
    bg = ImageDraw.Draw(badge_glow)
    bg.rounded_rectangle((78, 76, 239, 237), radius=44, fill=(143, 79, 255, 180))
    badge_glow = badge_glow.filter(ImageFilter.GaussianBlur(25))
    image = Image.alpha_composite(image, badge_glow)
    draw = ImageDraw.Draw(image)

    cx, cy = 158, 156
    star = [
        (cx, cy - 55), (cx + 15, cy - 15), (cx + 55, cy), (cx + 15, cy + 15),
        (cx, cy + 55), (cx - 15, cy + 15), (cx - 55, cy), (cx - 15, cy - 15),
    ]
    draw.polygon(star, fill='white')

    draw.text((290, 72), 'Clarify', font=_font(92, True), fill=(247, 251, 255, 255))
    draw.text((294, 176), 'AI Workspace inside Telegram', font=_font(34), fill=(158, 179, 214, 255))

    draw.text((78, 345), 'Send anything.', font=_font(60, True), fill=(246, 250, 255, 255))
    draw.text((78, 420), 'Get clarity.', font=_font(60, True), fill=(147, 115, 255, 255))
    draw.text(
        (82, 518),
        'Voice  •  Docs  •  Screens  •  Links  •  AI answers',
        font=_font(28),
        fill=(164, 181, 210, 255),
    )

    draw.rounded_rectangle((1040, 530, 1315, 610), radius=40, fill=(255, 255, 255, 22), outline=(116, 145, 255, 90), width=2)
    draw.text((1090, 550), 'CLARIFY ✦', font=_font(29, True), fill=(231, 239, 255, 255))

    output = BytesIO()
    image.convert('RGB').save(output, format='JPEG', quality=92, optimize=True, progressive=True)
    return output.getvalue()
