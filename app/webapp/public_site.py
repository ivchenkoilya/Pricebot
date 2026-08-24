from __future__ import annotations

import html
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.payments.yookassa import YooKassaClient

router = APIRouter(tags=['clarify-public-site'])
_APP_DIR = Path(__file__).resolve().parents[1]
_LOGO = _APP_DIR / 'banner_data' / 'clarify_logo.webp'
_ASSETS = Path(__file__).resolve().parent / 'public_assets'


def _env(name: str, default: str = '') -> str:
    return os.getenv(name, default).strip()


def _price(name: str, default: int) -> int:
    try:
        return max(1, int(_env(name, str(default))))
    except ValueError:
        return default


def _seller() -> dict[str, str]:
    return {k: html.escape(_env(v, 'Не заполнено')) for k, v in {
        'name': 'PUBLIC_SELLER_NAME', 'inn': 'PUBLIC_SELLER_INN',
        'email': 'PUBLIC_SELLER_EMAIL', 'support': 'PUBLIC_SUPPORT_CONTACT',
    }.items()}


def _ready(request: Request) -> bool:
    return YooKassaClient(request.app.state.settings).configured


def _layout(title: str, body: str, description: str = '', extra: str = '') -> HTMLResponse:
    desc = description or 'Clarify — AI-помощник для голосовых, документов, сообщений и изображений.'
    return HTMLResponse(f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#040713"><meta name="color-scheme" content="dark"><title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}"><link rel="stylesheet" href="/public-assets/site.css?v=2"></head><body><div class="live"><canvas id="fx"></canvas><div class="orb a"></div><div class="orb b"></div><div class="orb c"></div></div><nav><div class="wrap nav"><a class="brand" href="/"><img class="logo" src="/assets/clarify-logo.webp" alt="Clarify"><span>Clarify</span></a><div class="links"><a href="/#features">Возможности</a><a href="/#how">Как работает</a><a href="/pro">Тарифы</a><a href="/requisites">Реквизиты</a></div><a class="navbtn" href="/telegram/open">Открыть в Telegram ↗</a></div></nav>{body}<footer><div class="wrap foot"><span>© 2026 Clarify</span><div><a href="/requisites">Реквизиты</a><a href="/offer">Оферта</a><a href="/privacy">Конфиденциальность</a></div></div></footer><script src="/public-assets/site.js?v=2" defer></script>{extra}</body></html>''')


@router.get('/assets/clarify-logo.webp')
async def clarify_logo():
    if not _LOGO.exists():
        return RedirectResponse('/assets/clarify-banner.webp')
    return FileResponse(_LOGO, media_type='image/webp', headers={'Cache-Control': 'public,max-age=86400,immutable'})


@router.get('/public-assets/site.css')
async def site_css():
    return FileResponse(_ASSETS / 'site.css', media_type='text/css', headers={'Cache-Control': 'public,max-age=3600'})


@router.get('/public-assets/site.js')
async def site_js():
    return FileResponse(_ASSETS / 'site.js', media_type='application/javascript', headers={'Cache-Control': 'public,max-age=3600'})


@router.get('/telegram/open')
async def open_telegram(request: Request):
    direct = _env('PUBLIC_TELEGRAM_APP_URL')
    if direct.startswith('https://t.me/'):
        return RedirectResponse(direct)
    ctx = getattr(request.app.state, 'ctx', None)
    if ctx:
        try:
            me = await ctx.bot.get_me()
            if me.username:
                return RedirectResponse(f'https://t.me/{me.username}?startapp=site')
        except Exception:
            pass
    return RedirectResponse('/app/')


@router.get('/', response_class=HTMLResponse)
async def home(request: Request):
    body = '''<main class="wrap hero"><div><span class="tag"><span class="dot"></span>AI-помощник внутри Telegram</span><h1>Отправь что угодно.<br><span class="grad">Получи разбор.</span></h1><p class="lead">Clarify превращает голосовые, документы, переписки, скриншоты и ссылки в ясные выводы, задачи, сроки и готовые действия — за несколько секунд.</p><div class="actions"><a class="btn primary" href="/telegram/open">Открыть Clarify ↗</a><a class="btn" href="/pro">Смотреть тарифы</a></div><div class="chips"><span class="chip">🎙 Голос</span><span class="chip">📄 Документы</span><span class="chip">💬 Сообщения</span><span class="chip">🖼 Скриншоты</span></div></div><div class="visual"><div class="halo"></div><div class="heroimg"><img src="/assets/clarify-banner.webp" alt="Clarify"></div></div></main><section id="features"><div class="wrap"><div class="head"><div class="kicker">Возможности</div><h2>Информация перестаёт быть <span class="grad">хаосом</span></h2><p class="lead">Не переслушивай длинные голосовые и не перечитывай десятки страниц. Clarify сразу показывает то, что действительно важно.</p></div><div class="grid"><div class="card"><div class="ibox">🎙</div><h3>Голос и аудио</h3><p>Расшифровка, суть, задачи, решения и важные формулировки.</p></div><div class="card"><div class="ibox">📄</div><h3>Документы</h3><p>PDF, DOCX и таблицы: сроки, суммы, обязательства, условия и риски.</p></div><div class="card"><div class="ibox">💬</div><h3>Переписки</h3><p>Пойми, чего от тебя хотят, и подготовь естественный ответ.</p></div></div></div></section><section id="how"><div class="wrap"><div class="head"><div class="kicker">Как это работает</div><h2>Три шага. <span class="grad">Никакой рутины.</span></h2></div><div class="steps"><div class="card step"><h3>Отправляешь</h3><p>Голосовое, файл, фото, текст, переписку или ссылку.</p></div><div class="card step"><h3>Clarify разбирает</h3><p>Извлекает содержание и собирает главное без лишней воды.</p></div><div class="card step"><h3>Продолжаешь диалог</h3><p>Спрашиваешь о сроках, рисках, цене или просишь написать ответ.</p></div></div></div></section><section><div class="wrap"><div class="strip"><div><div class="kicker">Clarify PRO</div><h2>Для тех, кто использует Clarify каждый день</h2><p>Больше запросов, длинные голосовые, большие документы, Smart AI, Memory и проекты.</p></div><a class="btn primary" href="/pro">Выбрать тариф</a></div></div></section>'''
    return _layout('Clarify — отправь что угодно, получи разбор', body)


@router.get('/pro', response_class=HTMLResponse)
async def pro(request: Request):
    p, m = _price('PRO_RUB_PRICE', 299), _price('MAX_RUB_PRICE', 499)
    status = 'Оплата картой и СБП подключена через ЮKassa.' if _ready(request) else 'Карты и СБП подключаются. Telegram Stars уже доступны внутри Clarify.'
    body = f'''<section class="page"><div class="wrap"><span class="tag"><span class="dot"></span>Тарифы Clarify</span><h1 style="font-size:clamp(48px,6vw,75px)">Выбери свой <span class="grad">режим работы</span></h1><p class="lead">{status}</p><div class="prices"><div class="card price"><div class="ptop"><h3>FREE</h3></div><p>Для знакомства</p><div class="money">0 ₽</div><div class="period">навсегда</div><ul><li>20 AI-запросов в день</li><li>Голосовые до 10 минут</li><li>Документы до 15 страниц</li><li>Memory и Fast AI</li></ul><a class="btn" href="/telegram/open">Начать бесплатно</a></div><div class="card price featured"><div class="ptop"><h3>PRO</h3><span class="badge">ПОПУЛЯРНЫЙ</span></div><p>Для ежедневной работы</p><div class="money">{p} ₽</div><div class="period">30 дней</div><ul><li>До 100 AI-запросов в день</li><li>Голосовые до 30 минут</li><li>Документы до 100 страниц</li><li>Smart AI, Memory и проекты</li></ul><a class="btn primary" href="/pay?plan=pro">Выбрать PRO</a></div><div class="card price"><div class="ptop"><h3>PRO MAX</h3></div><p>Для активной работы</p><div class="money">{m} ₽</div><div class="period">30 дней</div><ul><li>До 250 AI-запросов в день</li><li>Голосовые до 60 минут</li><li>Документы до 200 страниц</li><li>Максимальные лимиты и приоритет</li></ul><a class="btn primary" href="/pay?plan=max">Выбрать MAX</a></div></div></div></section>'''
    return _layout('Clarify PRO — тарифы', body)


@router.get('/pay', response_class=HTMLResponse)
async def pay(request: Request, plan: str = 'pro'):
    plan = 'max' if plan.lower() == 'max' else 'pro'
    title = 'PRO MAX' if plan == 'max' else 'PRO'
    price = _price('MAX_RUB_PRICE', 499) if plan == 'max' else _price('PRO_RUB_PRICE', 299)
    if _ready(request):
        form = f'''<form id="form" class="form" data-plan="{plan}"><div class="field"><label>Telegram username</label><input id="username" placeholder="@username" required></div><div class="field"><label>Email для чека (если нужен)</label><input id="email" type="email" placeholder="mail@example.com"></div><div id="err" class="err"></div><button id="pay" class="btn primary" type="submit">Оплатить {price} ₽</button><div class="note">Сначала открой Clarify в Telegram хотя бы один раз. Данные карты Clarify не получает — платёж проходит на стороне ЮKassa.</div></form>'''
    else:
        form = '<div class="notice">Приём карт и СБП станет доступен сразу после активации магазина ЮKassa. Оплата Stars остаётся доступной внутри Telegram.</div>'
    body = f'''<section class="page"><div class="wrap pay"><span class="tag"><span class="dot"></span>Безопасная оплата</span><h1 style="font-size:clamp(48px,6vw,70px)">Clarify {title}</h1><div class="card paycard"><div class="payhead"><div><h3>{title} · 30 дней</h3><p>Автоматическая активация в аккаунте Clarify.</p></div><div class="payprice">{price} ₽</div></div><div class="label">Способы оплаты</div><div class="methods"><div class="method"><div class="mi">⚡</div><div><b>СБП</b><span>Через приложение банка</span></div></div><div class="method"><div class="mi">▣</div><div><b>Банковская карта</b><span>Через защищённую страницу ЮKassa</span></div></div></div><div class="after"><h3>После оплаты</h3><ul><li>Тариф активируется автоматически на 30 дней</li><li>Подтверждение придёт в Telegram</li><li>Доступ появится в том же аккаунте Clarify</li></ul></div>{form}<div class="actions"><a class="btn" href="/telegram/open">Открыть Clarify в Telegram</a><a class="btn" href="/pro">Назад к тарифам</a></div></div></div></section>'''
    script = '''<script>(()=>{const f=document.getElementById('form');if(!f)return;f.onsubmit=async e=>{e.preventDefault();const b=document.getElementById('pay'),er=document.getElementById('err');er.style.display='none';b.disabled=true;b.textContent='Создаём платёж…';try{const r=await fetch('/public-api/payments/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:f.dataset.plan,username:document.getElementById('username').value.trim(),email:document.getElementById('email').value.trim()||null})}),d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'Не удалось создать платёж');location.href=d.confirmation_url}catch(x){er.textContent=x.message;er.style.display='block';b.disabled=false;b.textContent='Попробовать снова'}}})();</script>'''
    return _layout(f'Оплата Clarify {title}', body, extra=script)


@router.get('/payment/success', response_class=HTMLResponse)
async def success(request: Request):
    body = '''<section class="page"><div class="wrap"><div class="card success"><div class="check">✓</div><div class="kicker">Платёж возвращён в Clarify</div><h2>Спасибо за покупку</h2><p class="lead">После подтверждения ЮKassa тариф активируется автоматически. Обычно это занимает несколько секунд.</p><div class="actions" style="justify-content:center"><a class="btn primary" href="/telegram/open">Открыть Clarify</a><a class="btn" href="/pro">Тарифы</a></div></div></div></section>'''
    return _layout('Оплата Clarify — готово', body)


@router.get('/requisites', response_class=HTMLResponse)
async def requisites(request: Request):
    s = _seller()
    warn = '<div class="notice">Юридические реквизиты ещё заполняются.</div>' if 'Не заполнено' in s.values() else ''
    body = f'''<section class="page"><div class="wrap legal"><span class="tag"><span class="dot"></span>Юридическая информация</span><h1 style="font-size:clamp(48px,6vw,70px)">Реквизиты</h1>{warn}<div class="table"><div>Продавец</div><div>{s['name']}</div><div>ИНН</div><div>{s['inn']}</div><div>Email</div><div>{s['email']}</div><div>Поддержка</div><div>{s['support']}</div></div><p>Clarify — программный AI-помощник для обработки пользовательских материалов.</p></div></section>'''
    return _layout('Clarify — реквизиты', body)


@router.get('/offer', response_class=HTMLResponse)
async def offer(request: Request):
    s = _seller()
    body = f'''<section class="page"><div class="wrap legal"><span class="tag"><span class="dot"></span>Документы</span><h1 style="font-size:clamp(48px,6vw,70px)">Публичная оферта</h1><p>Настоящий документ является предложением продавца <b>{s['name']}</b>, ИНН <b>{s['inn']}</b>, заключить договор на предоставление доступа к Clarify.</p><h2>1. Предмет</h2><p>Продавец предоставляет доступ к цифровому сервису Clarify и выбранному тарифу на оплаченный период.</p><h2>2. Стоимость и оплата</h2><p>Актуальная стоимость указана на странице <a href="/pro">тарифов</a>. Оплата считается подтверждённой после ответа платёжного провайдера.</p><h2>3. Доступ</h2><p>Доступ активируется после успешной оплаты и действует в течение периода, указанного при покупке.</p><h2>4. Возвраты</h2><p>Запросы по ошибочным платежам и возвратам рассматриваются через поддержку по применимому законодательству и правилам платёжного провайдера.</p><h2>5. Контакты</h2><p>Email: <b>{s['email']}</b>. Поддержка: <b>{s['support']}</b>.</p></div></section>'''
    return _layout('Clarify — публичная оферта', body)


@router.get('/privacy', response_class=HTMLResponse)
async def privacy(request: Request):
    s = _seller()
    body = f'''<section class="page"><div class="wrap legal"><span class="tag"><span class="dot"></span>Документы</span><h1 style="font-size:clamp(48px,6vw,70px)">Политика конфиденциальности</h1><p>Clarify обрабатывает данные, которые пользователь добровольно передаёт сервису: идентификатор Telegram, текст, файлы, голосовые, изображения, настройки и необходимые технические сведения.</p><h2>1. Цели</h2><p>Работа функций Clarify, хранение материалов, поддержка аккаунта, учёт тарифов и платежей, безопасность и диагностика ошибок.</p><h2>2. Платежи</h2><p>Данные банковской карты не хранятся на серверах Clarify. Платёжные данные обрабатываются платёжным провайдером; Clarify получает статус и идентификатор платежа для активации тарифа.</p><h2>3. Удаление</h2><p>Пользователь может удалять свои материалы средствами Clarify. Технические данные могут храниться дольше, если это требуется для безопасности, расчётов или юридических обязанностей.</p><h2>4. Контакты</h2><p>По вопросам обработки данных: <b>{s['email']}</b>.</p></div></section>'''
    return _layout('Clarify — политика конфиденциальности', body)
