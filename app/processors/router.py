from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class InputKind(StrEnum):
    TEXT = 'TEXT'
    VOICE = 'VOICE'
    AUDIO = 'AUDIO'
    IMAGE = 'IMAGE'
    SCREENSHOT = 'SCREENSHOT'
    PDF = 'PDF'
    DOCX = 'DOCX'
    TXT = 'TXT'
    MD = 'MD'
    XLSX = 'XLSX'
    CSV = 'CSV'
    FORWARDED_MESSAGE = 'FORWARDED_MESSAGE'
    UNKNOWN = 'UNKNOWN'


def classify(
    *,
    text: bool = False,
    voice: bool = False,
    audio: bool = False,
    photo: bool = False,
    forwarded: bool = False,
    filename: str | None = None,
) -> InputKind:
    if forwarded and text:
        return InputKind.FORWARDED_MESSAGE
    if voice:
        return InputKind.VOICE
    if audio:
        return InputKind.AUDIO
    if photo:
        return InputKind.IMAGE
    if filename:
        ext = Path(filename).suffix.lower()
        return {
            '.pdf': InputKind.PDF,
            '.docx': InputKind.DOCX,
            '.txt': InputKind.TXT,
            '.md': InputKind.MD,
            '.xlsx': InputKind.XLSX,
            '.csv': InputKind.CSV,
        }.get(ext, InputKind.UNKNOWN)
    if text:
        return InputKind.TEXT
    return InputKind.UNKNOWN
