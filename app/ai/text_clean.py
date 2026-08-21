from __future__ import annotations

import re


_MARKDOWN_LINK_RE = re.compile(r'\[([^\]\n]+)\]\((https?://[^)\s]+)\)')


def clean_display_text(value: object) -> str:
    """Convert model markdown-ish output into clean plain text.

    Clarify uses Telegram HTML for its own UI chrome. Model answers, however,
    sometimes contain Markdown such as ``**bold**`` or ``## heading``. Escaping
    those answers is safe, but leaves the Markdown punctuation visible to users.
    This function removes only presentation markup while preserving the words,
    lists, URLs and line breaks.
    """
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return ''

    # Fenced/inline code markers are presentation syntax. Keep their contents.
    text = re.sub(r'(?m)^\s*```[A-Za-z0-9_+.-]*\s*$', '', text)
    text = text.replace('```', '')
    text = re.sub(r'`([^`\n]+)`', r'\1', text)

    # Markdown headings and horizontal separators.
    text = re.sub(r'(?m)^\s{0,3}#{1,6}\s+', '', text)
    text = re.sub(r'(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$', '', text)

    # Links stay readable even though Telegram will auto-link the URL.
    text = _MARKDOWN_LINK_RE.sub(r'\1 — \2', text)

    # Bold / underline-style emphasis / strike-through.
    # Work line-by-line so malformed model output cannot eat whole paragraphs.
    text = re.sub(r'\*\*([^*\n]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_\n]+)__', r'\1', text)
    text = re.sub(r'~~([^~\n]+)~~', r'\1', text)

    # Asterisk bullets are converted to a neutral bullet; dash lists are kept.
    text = re.sub(r'(?m)^\s*\*\s+', '• ', text)

    # Remove excessive empty lines created by stripped separators/fences.
    text = re.sub(r'\n[ \t]+\n', '\n\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
