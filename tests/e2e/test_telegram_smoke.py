from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest


E2E_ENABLED = os.getenv('CLARIFY_E2E', '').strip() == '1'
pytestmark = pytest.mark.skipif(not E2E_ENABLED, reason='Set CLARIFY_E2E=1 to run Telegram user E2E')


def _required(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        pytest.skip(f'{name} is required for Telegram E2E')
    return value


async def _wait_bot_reply(client, bot, after_id: int, timeout: float = 35.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = await client.get_messages(bot, limit=8)
        for item in messages:
            if item.id > after_id and not item.out:
                return item
        await asyncio.sleep(0.5)
    raise AssertionError(f'Clarify did not reply within {timeout:.0f}s')


async def _scenario(client, bot, label: str, sender, *, timeout: float = 35.0, contains: str | None = None):
    before = await client.get_messages(bot, limit=1)
    before_id = before[0].id if before else 0
    started = time.perf_counter()
    await sender()
    reply = await _wait_bot_reply(client, bot, before_id, timeout=timeout)
    elapsed = time.perf_counter() - started
    text = (reply.raw_text or '').strip()
    if contains is not None:
        assert contains.lower() in text.lower(), f'{label}: expected {contains!r}, got {text[:500]!r}'
    print(f'{label:.<34} PASS {elapsed:5.1f}s')
    return reply, elapsed


@pytest.mark.asyncio
async def test_real_telegram_smoke():
    telethon = pytest.importorskip('telethon')
    TelegramClient = telethon.TelegramClient
    StringSession = pytest.importorskip('telethon.sessions').StringSession

    api_id = int(_required('CLARIFY_E2E_API_ID'))
    api_hash = _required('CLARIFY_E2E_API_HASH')
    session = _required('CLARIFY_E2E_SESSION')
    username = _required('CLARIFY_E2E_BOT_USERNAME').lstrip('@')

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        bot = await client.get_entity(username)

        await _scenario(client, bot, '/start', lambda: client.send_message(bot, '/start'), timeout=20)
        await _scenario(
            client,
            bot,
            'plain text',
            lambda: client.send_message(bot, 'Ответь одним словом: готов'),
            timeout=25,
        )
        await _scenario(
            client,
            bot,
            'schemeless URL',
            lambda: client.send_message(bot, 'Что это за сайт: vk.ru'),
            timeout=30,
        )
        await _scenario(client, bot, '/support open', lambda: client.send_message(bot, '/support'), timeout=15)
        # Leave support mode immediately so later fixture scenarios can reach AI.
        await client.send_message(bot, '/cancel')
        await asyncio.sleep(1)

        fixture_specs = [
            ('image', 'CLARIFY_E2E_IMAGE', 35.0),
            ('voice', 'CLARIFY_E2E_VOICE', 45.0),
            ('document', 'CLARIFY_E2E_DOCUMENT', 55.0),
        ]
        for label, env_name, timeout in fixture_specs:
            raw_path = os.getenv(env_name, '').strip()
            if not raw_path:
                print(f'{label:.<34} SKIP no {env_name}')
                continue
            path = Path(raw_path)
            assert path.exists(), f'{env_name} does not exist: {path}'
            await _scenario(
                client,
                bot,
                label,
                lambda p=path: client.send_file(bot, str(p)),
                timeout=timeout,
            )
