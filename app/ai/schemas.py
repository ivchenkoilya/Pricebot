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

    def to_telegram(self, prefix: str = '🧠 <b>Материал разобран</b>') -> str:
        esc = lambda value: html.escape(str(value))
        parts = [prefix]
        if self.summary:
            parts += ['', '<b>Кратко</b>', esc(self.summary)]
        if self.key_points:
            parts += ['', '<b>Главное</b>'] + [f'• {esc(x)}' for x in self.key_points[:8]]
        if self.tasks:
            parts += ['', '<b>Задачи</b>'] + [f'☐ {esc(x)}' for x in self.tasks[:8]]
        if self.dates:
            parts += ['', '<b>Даты / сроки</b>', ', '.join(esc(x) for x in self.dates[:8])]
        if self.amounts:
            parts += ['', '<b>Суммы</b>', ', '.join(esc(x) for x in self.amounts[:8])]
        if self.warnings:
            parts += ['', '<b>Важно</b>'] + [f'⚠️ {esc(x)}' for x in self.warnings[:5]]
        return '\n'.join(parts)[:4000]
