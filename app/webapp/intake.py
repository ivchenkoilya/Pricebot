from __future__ import annotations

import asyncio
import base64
import logging
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
from app.processors.documents import DocumentTooLarge
from app.processors.text import TextProcessor
from app.services.core import bonus_requests, plan_document_max_pages, plan_voice_max_seconds
from app.services.document_analysis import analyze_and_store_document
from app.services.growth import build_referral_link
from app.services.media_downloader import MediaDownloadError, is_media_url
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-webapp-intake'])
logger = logging.getLogger('clarify.webapp.intake')
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


def _image_storage_suffix(suffix: str, mime: str) -> str:
    if suffix in IMAGE_SUFFIXES:
        return suffix
    return {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
    }.get(mime, '.jpg')


async def _persist_image_source(ctx, user_id: int, data: bytes, suffix: str, mime: str) -> Path:
    root = Path(ctx.settings.data_dir) / 'materials' / str(user_id)
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    path = root / f'{uuid.uuid4().hex}{_image_storage_suffix(suffix, mime)}'
    await asyncio.to_thread(path.write_bytes, data)
    return path


async def _ensure_ai_allowed(ctx, user) -> None:
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой вкладку «Тарифы» или докупи пакет запросов.')


async def _sync_referral_after_success(ctx, user) -> None:
    """Qualify a referral only after a material was successfully persisted."""
    try:
        reward = await ctx.growth.sync_conversion(int(user.telegram_id))
        if reward is None:
            return
        await ctx.bot.send_message(
            reward.referred_telegram_id,
            f'🎁 <b>Реферальный бонус начислен</b>\n\n'
            f'Первый успешный разбор готов — +{reward.amount} AI-запросов.',
        )
        await ctx.bot.send_message(
            reward.referrer_telegram_id,
            f'🎁 <b>Друг попробовал Clarify</b>\n\n'
            f'Его первый разбор готов. Тебе начислено +{reward.amount} AI-запросов.',
        )
    except Exception:
        # Referral UX must never turn a successful material analysis into an HTTP error.
        logger.exception('Could not sync Mini App referral for telegram_id=%s', user.telegram_id)


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
    await _sync_referral_after_success(ctx, user)
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
        source_path = await _persist_image_source(ctx, user.id, data, suffix, mime)
        try:
            item = await ctx.materials.create(
                user.id,
                'image',
                result.title or filename,
                extracted,
                result.summary,
                local_path=str(source_path),
            )
        except Exception:
            try:
                source_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        await _sync_referral_after_success(ctx, user)
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
            try:
                item = await analyze_and_store_document(ctx, user, str(temp_path), suffix, filename)
            except DocumentTooLarge as exc:
                raise HTTPException(413, f'{exc}. Более высокий лимит доступен во вкладке «Тарифы».') from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc) or 'В документе не удалось найти текст') from exc
            except Exception as exc:
                await ctx.errors.record(uuid.uuid4().hex, tg.id, 'webapp_intake_document', exc)
                raise HTTPException(502, 'Clarify временно не смог обработать документ') from exc
            await ctx.metrics.inc('material_open', user.id)
            await _sync_referral_after_success(ctx, user)
            return _material_payload(item)

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

    referral = await ctx.growth.stats(user.id)
    bot_user = await ctx.bot.get_me()
    return {
        'materials': materials_count,
        'projects': projects_count,
        'reminders': reminders_count,
        'ai_today': await ctx.usage.ai_count_today(user.id),
        'invited': referral.invited_total,
        'activated': referral.rewarded_total,
        'earned_requests': referral.earned_requests,
        'bonus_requests': bonus_requests(user),
        'referral_bonus': int(ctx.settings.referral_bonus_requests),
        'referral_link': build_referral_link(bot_user.username or '', int(user.telegram_id)),
        'source': referral.source,
        'campaign': referral.campaign,
    }
