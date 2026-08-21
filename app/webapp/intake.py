from __future__ import annotations

import asyncio
import base64
import mimetypes
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.razberi_models import Material, Project, Reminder
from app.processors.documents import DocumentTooLarge, extract_document
from app.processors.text import TextProcessor
from app.services.core import plan_document_max_pages, plan_voice_max_seconds
from app.services.media_downloader import MediaDownloadError, is_media_url
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-webapp-intake'])
URL_RE = re.compile(r'^https?://', re.I)
AUDIO_SUFFIXES = {'.mp3', '.wav', '.m4a', '.ogg', '.opus', '.webm', '.aac', '.flac'}
DOCUMENT_SUFFIXES = {'.pdf', '.docx', '.txt', '.md', '.xlsx', '.csv'}
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


class TextIntakeBody(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


class LinkIntakeBody(BaseModel):
    url: str = Field(min_length=8, max_length=3000)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


async def _user(ctx, tg: TelegramWebAppUser):
    return await ctx.users.upsert(_tg_namespace(tg))


def _material_payload(item: Material) -> dict:
    return {
        'id': item.id, 'type': item.type, 'title': item.title, 'summary': item.summary,
        'status': item.status, 'created_at': item.created_at.isoformat() + 'Z' if item.created_at else None,
        'text': item.extracted_text[:80_000],
    }


def _structured_analysis_text(result) -> str:
    parts: list[str] = []
    if result.summary: parts.append('Кратко:\n' + result.summary)
    if result.key_points: parts.append('Главное:\n' + '\n'.join(f'- {x}' for x in result.key_points))
    if result.tasks: parts.append('Задачи:\n' + '\n'.join(f'- {x}' for x in result.tasks))
    if result.dates: parts.append('Сроки и даты:\n' + '\n'.join(f'- {x}' for x in result.dates))
    if result.amounts: parts.append('Суммы:\n' + '\n'.join(f'- {x}' for x in result.amounts))
    if result.warnings: parts.append('Риски и предупреждения:\n' + '\n'.join(f'- {x}' for x in result.warnings))
    return '\n\n'.join(parts).strip()


def _audio_duration_seconds(path: Path) -> int:
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True, timeout=8, check=False,
        )
        return max(0, int(float((result.stdout or '0').strip() or 0)))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


async def _ensure_ai_allowed(ctx, user) -> None:
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой вкладку «Тарифы» или докупи пакет запросов.')


async def _analyze_and_store(ctx, user, source_text: str, kind: str, material_type: str, operation: str):
    await _ensure_ai_allowed(ctx, user)
    try:
        result, usage, model = await TextProcessor(ctx.ai).process(source_text, kind)
    except Exception as exc:
        await ctx.errors.record(uuid.uuid4().hex, user.telegram_id, f'webapp_intake_{operation}', exc)
        raise HTTPException(502, 'Clarify временно не смог разобрать материал') from exc
    await ctx.usage.record(user.id, model, f'webapp_intake_{operation}', usage)
    item = await ctx.materials.create(user.id, material_type, result.title, source_text, result.summary)
    await ctx.metrics.inc('material_open', user.id)
    return _material_payload(item)


@router.post('/intake/text')
async def intake_text(body: TextIntakeBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request); user = await _user(ctx, tg)
    return await _analyze_and_store(ctx, user, body.text.strip(), 'текст', 'text', 'text')


@router.post('/intake/link')
async def intake_link(body: LinkIntakeBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request); user = await _user(ctx, tg); url = body.url.strip()
    if not URL_RE.match(url): raise HTTPException(400, 'Ссылка должна начинаться с http:// или https://')
    if is_media_url(url):
        try:
            info = await ctx.media_downloader.inspect(url)
            transcript = await ctx.media_downloader.fast_transcript(url)
        except MediaDownloadError as exc:
            raise HTTPException(400, str(exc)) from exc
        source_text = transcript.strip() if transcript else f'Видео-ссылка: {url}\nПлатформа: {info.platform}\nНазвание: {info.title}\nАвтор: {info.author or "не указан"}'
        return await _analyze_and_store(ctx, user, source_text, 'транскрипт видео' if transcript else 'видео-ссылка', 'video', 'video_link')
    try:
        page = await ctx.page_reader.read(url)
    except Exception as exc:
        await ctx.errors.record(uuid.uuid4().hex, tg.id, 'webapp_intake_link_read', exc)
        raise HTTPException(400, 'Не получилось прочитать эту страницу. Попробуй другую публичную ссылку.') from exc
    text = page.text.strip()
    if not text: raise HTTPException(400, 'На странице не удалось найти текст для разбора')
    return await _analyze_and_store(ctx, user, text, f'веб-страницу {page.host}', 'link', 'link')


@router.post('/intake/file')
async def intake_file(request: Request, file: UploadFile = File(...), tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request); user = await _user(ctx, tg); await _ensure_ai_allowed(ctx, user)
    filename = (file.filename or 'material').strip()[:180]
    suffix = Path(filename).suffix.lower()
    mime = (file.content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream').lower()
    max_bytes = int(ctx.settings.max_file_size_mb) * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes: raise HTTPException(413, f'Файл больше лимита {ctx.settings.max_file_size_mb} МБ')
    if not data: raise HTTPException(400, 'Файл пустой')

    if mime.startswith('image/') or suffix in IMAGE_SUFFIXES:
        try:
            result, usage, model, _raw = await ctx.ai.analyze_image(base64.b64encode(data).decode('ascii'), mime if mime.startswith('image/') else 'image/jpeg', 'Разбери изображение или скриншот')
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, tg.id, 'webapp_intake_image', exc)
            raise HTTPException(502, 'Clarify временно не смог разобрать изображение') from exc
        await ctx.usage.record(user.id, model, 'webapp_intake_image', usage)
        extracted = _structured_analysis_text(result) or result.summary or filename
        item = await ctx.materials.create(user.id, 'image', result.title or filename, extracted, result.summary)
        return _material_payload(item)

    temp_root = Path(ctx.settings.data_dir) / 'tmp' / 'webapp-intake'; temp_root.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or '.bin', dir=temp_root) as tmp:
            tmp.write(data); temp_path = Path(tmp.name)

        if mime.startswith('audio/') or suffix in AUDIO_SUFFIXES:
            duration = await asyncio.to_thread(_audio_duration_seconds, temp_path)
            max_seconds = plan_voice_max_seconds(user, ctx.settings)
            if max_seconds is not None and duration > max_seconds:
                raise HTTPException(413, f'Твой тариф поддерживает аудио до {max_seconds // 60} минут. Открой «Тарифы», чтобы увеличить лимит.')
            try:
                async with ctx.stt_sem: transcript = await ctx.stt.transcribe(str(temp_path), 'ru')
            except Exception as exc:
                await ctx.errors.record(uuid.uuid4().hex, tg.id, 'webapp_intake_audio_stt', exc)
                raise HTTPException(502, 'Не получилось распознать аудио') from exc
            transcript = (transcript or '').strip()
            if not transcript: raise HTTPException(400, 'В аудио не удалось обнаружить речь')
            return await _analyze_and_store(ctx, user, transcript, 'аудио', 'audio', 'audio')

        if suffix in DOCUMENT_SUFFIXES:
            max_pages = plan_document_max_pages(user, ctx.settings)
            try:
                extracted, _pages, material_type = extract_document(str(temp_path), suffix, max_pages)
            except DocumentTooLarge as exc:
                raise HTTPException(413, f'{exc}. Более высокий лимит доступен во вкладке «Тарифы».') from exc
            except Exception as exc:
                raise HTTPException(400, 'Не получилось прочитать этот документ') from exc
            extracted = (extracted or '').strip()
            if not extracted: raise HTTPException(400, 'В документе не удалось найти текст')
            return await _analyze_and_store(ctx, user, extracted, f'документ {filename}', material_type, 'document')

        raise HTTPException(415, 'Поддерживаются изображения, аудио, PDF, DOCX, TXT, MD, XLSX и CSV')
    finally:
        if temp_path:
            try: temp_path.unlink(missing_ok=True)
            except OSError: pass


@router.get('/profile/stats')
async def profile_stats(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request); user = await _user(ctx, tg)
    async with ctx.db.sessions() as db:
        materials_count = int((await db.execute(select(func.count(Material.id)).where(Material.user_id == user.id))).scalar() or 0)
        projects_count = int((await db.execute(select(func.count(Project.id)).where(Project.user_id == user.id))).scalar() or 0)
        reminders_count = int((await db.execute(select(func.count(Reminder.id)).where(Reminder.user_id == user.id, Reminder.status == 'active'))).scalar() or 0)
    return {'materials': materials_count, 'projects': projects_count, 'reminders': reminders_count, 'ai_today': await ctx.usage.ai_count_today(user.id)}
