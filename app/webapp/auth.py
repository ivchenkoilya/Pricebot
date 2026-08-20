from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request, status


@dataclass(slots=True, frozen=True)
class TelegramWebAppUser:
    id: int
    first_name: str = ''
    last_name: str = ''
    username: str | None = None
    language_code: str | None = None
    photo_url: str | None = None


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86_400) -> TelegramWebAppUser:
    if not init_data or not bot_token:
        raise ValueError('initData or BOT_TOKEN is missing')

    values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = values.pop('hash', '')
    if not received_hash:
        raise ValueError('hash is missing')

    check_string = '\n'.join(f'{key}={values[key]}' for key in sorted(values))
    secret_key = hmac.new(b'WebAppData', bot_token.encode('utf-8'), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise ValueError('invalid hash')

    try:
        auth_date = int(values.get('auth_date', '0'))
    except ValueError as exc:
        raise ValueError('invalid auth_date') from exc
    if auth_date <= 0:
        raise ValueError('auth_date is missing')
    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise ValueError('initData expired')
    if auth_date - time.time() > 60:
        raise ValueError('auth_date is in the future')

    try:
        payload = json.loads(values.get('user', '{}'))
        user_id = int(payload['id'])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('user payload is invalid') from exc

    return TelegramWebAppUser(
        id=user_id,
        first_name=str(payload.get('first_name') or ''),
        last_name=str(payload.get('last_name') or ''),
        username=str(payload['username']) if payload.get('username') else None,
        language_code=str(payload['language_code']) if payload.get('language_code') else None,
        photo_url=str(payload['photo_url']) if payload.get('photo_url') else None,
    )


def _dev_user(request: Request):
    settings = request.app.state.settings
    if not (settings.test_mode and settings.webapp_dev_auth):
        return None
    raw = request.headers.get('x-dev-telegram-user', '').strip()
    if not raw:
        return None
    try:
        telegram_id = int(raw)
    except ValueError:
        return None
    return TelegramWebAppUser(id=telegram_id, first_name='Dev')


async def telegram_webapp_user(request: Request) -> TelegramWebAppUser:
    dev = _dev_user(request)
    if dev is not None:
        return dev

    authorization = request.headers.get('authorization', '')
    init_data = request.headers.get('x-telegram-init-data', '')
    if authorization.lower().startswith('tma '):
        init_data = authorization[4:].strip()
    if not init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Open Clarify inside Telegram')

    try:
        return validate_init_data(
            init_data,
            request.app.state.settings.bot_token,
            request.app.state.settings.webapp_auth_max_age_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def runtime_context(request: Request):
    ctx = getattr(request.app.state, 'ctx', None)
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Clarify is starting')
    return ctx
