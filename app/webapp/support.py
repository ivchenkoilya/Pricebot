from __future__ import annotations

import html
import uuid
from types import SimpleNamespace

from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.services.core import is_active_pro, is_creator
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-support'])

CATEGORY_LABELS = {
    'bug': '🐞 Ошибка',
    'idea': '💡 Идея',
    'question': '🛟 Поддержка',
    'other': '💬 Сообщение',
}


class SupportBody(BaseModel):
    kind: str = Field(default='question', max_length=24)
    message: str = Field(min_length=2, max_length=4000)
    page: str | None = Field(default=None, max_length=120)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


def _support_text(*, tg: TelegramWebAppUser, user, settings, kind: str, message: str, page: str | None) -> str:
    label = CATEGORY_LABELS.get(kind, CATEGORY_LABELS['other'])
    username = f'@{tg.username}' if tg.username else 'не указан'
    plan = 'OWNER' if is_creator(user, settings) else ('PRO' if is_active_pro(user) else 'FREE')
    page_text = (page or 'не указана').strip()[:120]
    return (
        f'<b>🛟 Clarify · {label}</b>\n\n'
        f'<b>Пользователь:</b> <a href="tg://user?id={tg.id}">{html.escape(tg.first_name or "User")}</a>\n'
        f'<b>Username:</b> {html.escape(username)}\n'
        f'<b>Telegram ID:</b> <code>{tg.id}</code>\n'
        f'<b>Тариф:</b> {html.escape(plan)}\n'
        f'<b>Версия:</b> {html.escape(settings.version)}\n'
        f'<b>Экран:</b> {html.escape(page_text)}\n\n'
        f'<b>Сообщение:</b>\n{html.escape(message.strip())}'
    )


async def _deliver(request: Request, tg: TelegramWebAppUser, *, kind: str, message: str, page: str | None, screenshot: bytes | None = None, filename: str = 'screenshot.jpg'):
    ctx = runtime_context(request)
    admin_id = ctx.settings.admin_telegram_id
    if not admin_id:
        raise HTTPException(503, 'Поддержка пока не настроена. Попробуй позже.')

    user = await ctx.users.upsert(_tg_namespace(tg))
    text = _support_text(tg=tg, user=user, settings=ctx.settings, kind=kind, message=message, page=page)
    request_id = uuid.uuid4().hex
    try:
        await ctx.bot.send_message(admin_id, text, parse_mode='HTML')
        if screenshot:
            photo = BufferedInputFile(screenshot, filename=filename or 'screenshot.jpg')
            try:
                await ctx.bot.send_photo(admin_id, photo, caption=f'📎 Скриншот к обращению от {tg.id}')
            except Exception:
                await ctx.bot.send_document(admin_id, photo, caption=f'📎 Вложение к обращению от {tg.id}')
        await ctx.metrics.inc('support_submitted', user.id)
    except Exception as exc:
        await ctx.errors.record(request_id, tg.id, 'support_submit', exc)
        raise HTTPException(502, 'Не получилось отправить обращение. Попробуй ещё раз.') from exc

    return {'ok': True, 'request_id': request_id}


@router.post('/support')
async def support_submit(
    body: SupportBody,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    kind = body.kind if body.kind in CATEGORY_LABELS else 'other'
    return await _deliver(request, tg, kind=kind, message=body.message, page=body.page)


@router.post('/support/file')
async def support_submit_with_file(
    request: Request,
    kind: str = Form('question'),
    message: str = Form(...),
    page: str = Form(''),
    file: UploadFile = File(...),
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    if len(message.strip()) < 2:
        raise HTTPException(400, 'Опиши проблему или вопрос чуть подробнее.')
    if len(message) > 4000:
        raise HTTPException(400, 'Сообщение слишком длинное.')
    if not (file.content_type or '').startswith('image/'):
        raise HTTPException(400, 'Для обращения можно приложить изображение или скриншот.')
    data = await file.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, 'Скриншот слишком большой. Максимум 8 МБ.')
    safe_kind = kind if kind in CATEGORY_LABELS else 'other'
    return await _deliver(
        request,
        tg,
        kind=safe_kind,
        message=message,
        page=page,
        screenshot=data,
        filename=file.filename or 'screenshot.jpg',
    )
