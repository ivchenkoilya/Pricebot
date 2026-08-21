from __future__ import annotations

import io
import mimetypes
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-source-media'])
IMAGE_TYPES = {'image', 'screenshot'}


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


def _bytes_media_type(data: bytes) -> str:
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    return 'application/octet-stream'


@router.get('/materials/{material_id}/source-image')
async def material_source_image(
    material_id: int,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await ctx.users.upsert(_tg_namespace(tg))
    item = await ctx.materials.get(user.id, material_id)
    if not item:
        raise HTTPException(404, 'Материал не найден')
    if item.type not in IMAGE_TYPES:
        raise HTTPException(404, 'У материала нет изображения-исходника')

    if item.local_path:
        path = Path(item.local_path)
        if path.is_file():
            media_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            return FileResponse(path, media_type=media_type, headers={'Cache-Control': 'private, max-age=3600'})

    if item.telegram_file_id:
        buffer = io.BytesIO()
        try:
            await ctx.bot.download(item.telegram_file_id, destination=buffer)
        except Exception as exc:
            raise HTTPException(502, 'Не получилось загрузить исходное изображение из Telegram') from exc
        data = buffer.getvalue()
        if not data:
            raise HTTPException(404, 'Исходное изображение недоступно')
        return Response(content=data, media_type=_bytes_media_type(data), headers={'Cache-Control': 'private, max-age=3600'})

    raise HTTPException(404, 'Исходное изображение не сохранилось')
