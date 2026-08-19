from __future__ import annotations

import html
from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    title: str = 'Материал'
    summary: str = ''
    key_points: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_text: str = ''

    def to_telegram(self, prefix: str = '✨ <b>Clarify</b> · материал разобран') -> str:
        esc = lambda value: html.escape(str(value))
        parts = [prefix]
        if self.title and self.title != 'Материал':
            parts += [f'<b>{esc(self.title)}</b>']
        if self.summary:
            parts += ['', '<b>Коротко</b>', esc(self.summary)]
        if self.key_points:
            parts += ['', '<b>📌 Главное</b>'] + [f'• {esc(x)}' for x in self.key_points[:6]]
        if self.tasks:
            parts += ['', '<b>✅ Что сделать</b>'] + [f'☐ {esc(x)}' for x in self.tasks[:6]]
        if self.dates:
            parts += ['', f'<b>📅 Сроки · {len(self.dates)}</b>', ' • '.join(esc(x) for x in self.dates[:6])]
        if self.amounts:
            parts += ['', f'<b>💰 Деньги · {len(self.amounts)}</b>', ' • '.join(esc(x) for x in self.amounts[:6])]
        if self.warnings:
            parts += ['', f'<b>⚠️ Важно · {len(self.warnings)}</b>'] + [f'• {esc(x)}' for x in self.warnings[:4]]
        return '\n'.join(parts)[:4000]
