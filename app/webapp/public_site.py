from __future__ import annotations

import html
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=['clarify-public-site'])


def _env(name: str, default: str = '') -> str:
    return os.getenv(name, default).strip()


def _seller() -> dict[str, str]:
    return {
        'name': _env('PUBLIC_SELLER_NAME', 'Не заполнено'),
        'inn': _env('PUBLIC_SELLER_INN', 'Не заполнено'),
        'email': _env('PUBLIC_SELLER_EMAIL', 'Не заполнено'),
        'support': _env('PUBLIC_SUPPORT_CONTACT', '@clarify_support'),
    }


def _price(name: str, default: int) -> int:
    try:
        return max(1, int(_env(name, str(default))))
    except ValueError:
        return default


def _layout(title: str, body: str, *, description: str = 'Clarify — AI-помощник для голосовых, документов, сообщений и изображений.') -> HTMLResponse:
    safe_title = html.escape(title)
    safe_description = html.escape(description)
    return HTMLResponse(f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#050816">
<title>{safe_title}</title>
<meta name="description" content="{safe_description}">
<style>
:root{{--bg:#050816;--bg2:#09112b;--card:rgba(13,24,55,.82);--line:rgba(113,160,255,.22);--text:#f7f9ff;--muted:#a6b2d3;--blue:#40a9ff;--purple:#a86cff;--ok:#49e6b1}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 18% -8%,rgba(32,111,255,.30),transparent 34%),radial-gradient(circle at 92% 8%,rgba(161,70,255,.22),transparent 28%),linear-gradient(180deg,var(--bg),#03050d 76%);color:var(--text);min-height:100vh}}
a{{color:inherit;text-decoration:none}}.wrap{{width:min(1120px,calc(100% - 32px));margin:0 auto}}nav{{position:sticky;top:0;z-index:20;backdrop-filter:blur(18px);background:rgba(5,8,22,.78);border-bottom:1px solid rgba(255,255,255,.06)}}.nav{{height:72px;display:flex;align-items:center;justify-content:space-between;gap:18px}}.brand{{font-weight:850;font-size:21px;letter-spacing:-.5px;display:flex;align-items:center;gap:10px}}.spark{{width:30px;height:30px;border-radius:10px;background:linear-gradient(135deg,#6ce8ff,#2979ff 55%,#b260ff);box-shadow:0 0 28px rgba(58,151,255,.55)}}.links{{display:flex;gap:22px;color:var(--muted);font-size:14px}}.links a:hover{{color:#fff}}.hero{{padding:76px 0 44px;display:grid;grid-template-columns:1.08fr .92fr;align-items:center;gap:48px}}.eyebrow{{display:inline-flex;padding:8px 12px;border-radius:999px;border:1px solid rgba(87,174,255,.24);background:rgba(37,101,214,.12);color:#b9ddff;font-size:13px}}h1{{font-size:clamp(46px,7vw,78px);line-height:.98;letter-spacing:-3px;margin:18px 0 18px}}h2{{font-size:clamp(30px,4vw,48px);letter-spacing:-1.7px;margin:0 0 14px}}h3{{font-size:21px;margin:0 0 8px}}p{{color:var(--muted);line-height:1.65}}.lead{{font-size:19px;max-width:650px}}.grad{{background:linear-gradient(90deg,#fff 8%,#8fe1ff 50%,#b994ff);-webkit-background-clip:text;background-clip:text;color:transparent}}.actions{{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}}.btn{{display:inline-flex;align-items:center;justify-content:center;min-height:52px;padding:0 22px;border-radius:15px;font-weight:800;border:1px solid rgba(255,255,255,.08);transition:.18s ease;box-shadow:inset 0 1px rgba(255,255,255,.05)}}.btn:hover{{transform:translateY(-1px)}}.primary{{background:linear-gradient(135deg,#24b8ff,#476dff 55%,#9a54ff);box-shadow:0 14px 36px rgba(43,111,255,.28)}}.secondary{{background:rgba(255,255,255,.055)}}.banner{{border-radius:28px;overflow:hidden;border:1px solid rgba(255,255,255,.08);box-shadow:0 30px 80px rgba(0,0,0,.45),0 0 70px rgba(29,113,255,.16)}}.banner img{{width:100%;display:block}}section{{padding:58px 0}}.page-top{{padding-top:50px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.card{{background:linear-gradient(180deg,rgba(17,31,71,.90),rgba(8,15,35,.90));border:1px solid var(--line);border-radius:22px;padding:24px;box-shadow:inset 0 1px rgba(255,255,255,.04)}}.icon{{font-size:25px;margin-bottom:18px}}.price-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:28px;align-items:stretch}}.price{{position:relative;display:flex;flex-direction:column}}.price ul{{flex:1}}.featured{{border-color:rgba(80,166,255,.72);background:linear-gradient(180deg,rgba(18,42,94,.96),rgba(8,17,42,.94));box-shadow:0 0 0 1px rgba(88,168,255,.15),0 22px 70px rgba(44,105,255,.23),0 0 60px rgba(97,87,255,.10)}}.badge{{position:absolute;right:18px;top:18px;font-size:11px;font-weight:850;padding:6px 9px;border-radius:999px;background:linear-gradient(135deg,#1ca9ff,#536aff);box-shadow:0 8px 22px rgba(32,121,255,.28)}}.money{{font-size:42px;font-weight:880;letter-spacing:-2px;margin:18px 0 4px}}.period{{color:var(--muted);font-size:13px}}ul{{padding:0;margin:22px 0;list-style:none}}li{{margin:12px 0;color:#cbd5f4}}li:before{{content:'✓';color:var(--ok);margin-right:9px;font-weight:900}}.notice{{padding:16px 18px;border:1px solid rgba(255,190,70,.22);background:rgba(255,170,0,.07);border-radius:16px;color:#ead6a3}}.legal{{max-width:850px}}.legal h2{{margin-top:38px;font-size:28px}}.legal p,.legal li{{font-size:15px}}.table{{display:grid;grid-template-columns:220px 1fr;border:1px solid var(--line);border-radius:18px;overflow:hidden;margin-top:24px}}.table div{{padding:15px 16px;border-bottom:1px solid var(--line)}}.table div:nth-last-child(-n+2){{border-bottom:none}}.table div:nth-child(odd){{color:var(--muted);background:rgba(255,255,255,.025)}}.pay-card{{padding:28px}}.pay-head{{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;padding-bottom:22px;border-bottom:1px solid rgba(255,255,255,.07)}}.pay-price{{font-size:46px;font-weight:900;letter-spacing:-2px;white-space:nowrap}}.payment-title{{font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#91a4d6;margin:24px 0 12px}}.payment-methods{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.method{{display:flex;align-items:center;gap:12px;padding:16px;border-radius:17px;border:1px solid rgba(126,171,255,.18);background:rgba(255,255,255,.035)}}.method-icon{{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,rgba(41,176,255,.22),rgba(133,75,255,.24));font-size:20px}}.method strong{{display:block}}.method span{{display:block;color:var(--muted);font-size:12px;margin-top:2px}}.after-pay{{margin-top:18px;padding:18px;border-radius:17px;background:rgba(78,130,255,.07);border:1px solid rgba(95,151,255,.14)}}.after-pay h3{{font-size:16px;margin-bottom:12px}}.after-pay ul{{margin:0}}.after-pay li{{margin:8px 0;font-size:14px}}footer{{margin-top:50px;border-top:1px solid rgba(255,255,255,.07);padding:30px 0 44px;color:var(--muted);font-size:13px}}.foot{{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}}.disabled{{opacity:.58;cursor:not-allowed;transform:none!important}}
@media(max-width:820px){{
  .wrap{{width:min(100% - 28px,680px)}}
  .nav{{height:66px}}.brand{{font-size:20px}}.spark{{width:29px;height:29px}}.links{{display:none}}
  .hero{{grid-template-columns:1fr;padding:34px 0 28px;gap:28px}}
  section{{padding:34px 0}}.page-top{{padding-top:28px}}
  h1{{font-size:clamp(40px,12vw,58px)!important;line-height:1.01;letter-spacing:-2.2px;margin:16px 0 16px}}
  h2{{font-size:32px}}.lead{{font-size:17px;line-height:1.55}}
  .grid,.price-grid{{grid-template-columns:1fr;gap:16px}}
  .price-grid{{margin-top:22px}}.card{{border-radius:22px;padding:22px}}
  .price{{min-height:auto}}.price h3{{font-size:22px}}.money{{font-size:46px;margin-top:15px}}.price p{{margin-top:8px}}
  .price ul{{margin:20px 0 24px}}.price li{{font-size:16px;line-height:1.45;margin:12px 0}}
  .price .btn{{width:100%;min-height:56px;font-size:16px}}
  .featured{{box-shadow:0 0 0 1px rgba(88,168,255,.20),0 18px 50px rgba(44,105,255,.24),0 0 48px rgba(112,77,255,.13)}}
  .badge{{right:16px;top:16px;font-size:10px}}
  .actions{{gap:10px;margin-top:22px}}.actions .btn{{min-height:54px}}
  .pay-card{{padding:22px}}.pay-head{{align-items:flex-start;flex-direction:column;gap:4px;padding-bottom:18px}}
  .pay-price{{font-size:48px}}.payment-methods{{grid-template-columns:1fr}}.method{{padding:14px}}
  .notice{{font-size:14px;line-height:1.5;padding:14px 15px}}
  .pay-card .actions{{display:grid;grid-template-columns:1fr;gap:10px}}.pay-card .actions .btn{{width:100%}}
  .table{{grid-template-columns:1fr}}.table div:nth-child(odd){{padding-bottom:4px;border-bottom:none}}.table div:nth-child(even){{padding-top:4px}}
  footer{{margin-top:28px;padding:24px 0 34px}}.foot{{font-size:12px;line-height:1.7}}
}}
</style>
</head>
<body>
<nav><div class="wrap nav"><a class="brand" href="/"><span class="spark"></span>Clarify</a><div class="links"><a href="/#features">Возможности</a><a href="/pro">Тарифы</a><a href="/requisites">Реквизиты</a><a href="/offer">Оферта</a><a href="/privacy">Конфиденциальность</a></div></div></nav>
{body}
<footer><div class="wrap foot"><span>© 2026 Clarify</span><span><a href="/requisites">Реквизиты</a> · <a href="/offer">Оферта</a> · <a href="/privacy">Политика конфиденциальности</a></span></div></footer>
</body></html>''')


@router.get('/', response_class=HTMLResponse)
async def public_home(request: Request):
    body = '''
<main class="wrap hero">
  <div>
    <span class="eyebrow">AI workspace в Telegram</span>
    <h1>Отправь что угодно.<br><span class="grad">Получи разбор.</span></h1>
    <p class="lead">Clarify разбирает голосовые, документы, переписки, изображения и ссылки, выделяет главное и превращает информацию в понятные действия.</p>
    <div class="actions"><a class="btn primary" href="/pro">Смотреть тарифы</a><a class="btn secondary" href="/app/">Открыть Mini App</a></div>
  </div>
  <div class="banner"><img src="/assets/clarify-banner.webp" alt="Clarify"></div>
</main>
<section id="features"><div class="wrap"><h2>Всё важное — <span class="grad">в одном месте</span></h2><p>Не нужно вручную переслушивать голосовые и перечитывать длинные файлы.</p><div class="grid">
<div class="card"><div class="icon">🎙️</div><h3>Голос и аудио</h3><p>Расшифровка, краткое содержание, задачи и сроки.</p></div>
<div class="card"><div class="icon">📄</div><h3>Документы</h3><p>PDF, DOCX, таблицы и текстовые файлы — суммы, условия и риски.</p></div>
<div class="card"><div class="icon">💬</div><h3>Переписки</h3><p>Что от тебя хотят, что ответить и какие действия выполнить дальше.</p></div>
</div></div></section>
<section><div class="wrap"><div class="card"><h2>Clarify PRO</h2><p class="lead">Больше запросов, длинные голосовые, большие документы и Smart AI.</p><div class="actions"><a class="btn primary" href="/pro">Выбрать тариф</a></div></div></div></section>
'''
    return _layout('Clarify — AI-помощник', body)


@router.get('/pro', response_class=HTMLResponse)
async def public_pro(request: Request):
    pro = _price('PRO_RUB_PRICE', 299)
    max_price = _price('MAX_RUB_PRICE', 499)
    body = f'''
<section class="page-top"><div class="wrap"><span class="eyebrow">Тарифы Clarify</span><h1 style="font-size:clamp(42px,6vw,66px)">Выбери свой <span class="grad">режим работы</span></h1><p class="lead">Оплата картой и через СБП скоро появится через ЮKassa. В Telegram остаётся оплата Stars.</p>
<div class="price-grid">
<div class="card price"><h3>FREE</h3><p>Для знакомства</p><div class="money">0 ₽</div><div class="period">навсегда</div><ul><li>20 AI-запросов в день</li><li>Голосовые до 10 минут</li><li>Документы до 15 страниц</li><li>Memory и Fast AI</li></ul></div>
<div class="card price featured"><span class="badge">ПОПУЛЯРНЫЙ</span><h3>PRO</h3><p>Для ежедневной работы</p><div class="money">{pro} ₽</div><div class="period">30 дней</div><ul><li>До 100 AI-запросов в день</li><li>Голосовые до 30 минут</li><li>Документы до 100 страниц</li><li>Smart AI, Memory и проекты</li></ul><a class="btn primary" href="/pay?plan=pro">Оплатить PRO</a></div>
<div class="card price"><h3>PRO MAX</h3><p>Для активной работы</p><div class="money">{max_price} ₽</div><div class="period">30 дней</div><ul><li>До 250 AI-запросов в день</li><li>Голосовые до 60 минут</li><li>Документы до 200 страниц</li><li>Максимальные лимиты и приоритет</li></ul><a class="btn primary" href="/pay?plan=max">Оплатить PRO MAX</a></div>
</div></div></section>'''
    return _layout('Clarify PRO — тарифы', body, description='Тарифы Clarify FREE, PRO и PRO MAX.')


@router.get('/pay', response_class=HTMLResponse)
async def public_pay(request: Request, plan: str = 'pro'):
    plan = 'max' if plan.lower() == 'max' else 'pro'
    title = 'PRO MAX' if plan == 'max' else 'PRO'
    price = _price('MAX_RUB_PRICE', 499) if plan == 'max' else _price('PRO_RUB_PRICE', 299)
    limits = (
        ('До 250 AI-запросов в день', 'Голосовые до 60 минут', 'Документы до 200 страниц')
        if plan == 'max'
        else ('До 100 AI-запросов в день', 'Голосовые до 30 минут', 'Документы до 100 страниц')
    )
    body = f'''
<section class="page-top"><div class="wrap legal"><span class="eyebrow">Безопасная оплата</span><h1 style="font-size:clamp(40px,6vw,62px)">Clarify {title}</h1>
<div class="card pay-card">
  <div class="pay-head"><div><h3>{title} · 30 дней</h3><p style="margin:6px 0 0">Доступ активируется автоматически после успешной оплаты.</p></div><div class="pay-price">{price} ₽</div></div>
  <div class="payment-title">Способ оплаты</div>
  <div class="payment-methods">
    <div class="method"><div class="method-icon">⚡</div><div><strong>СБП</strong><span>Быстрая оплата по QR / приложению банка</span></div></div>
    <div class="method"><div class="method-icon">💳</div><div><strong>Банковская карта</strong><span>МИР и доступные банковские карты</span></div></div>
  </div>
  <div class="after-pay"><h3>Что входит в {title}</h3><ul><li>{limits[0]}</li><li>{limits[1]}</li><li>{limits[2]}</li><li>Тариф активируется сразу после подтверждения платежа</li></ul></div>
  <div class="notice" style="margin-top:18px">ЮKassa сейчас подключается. После подтверждения магазина эта страница будет создавать настоящий платёж, а Clarify автоматически включит тариф после успешной оплаты.</div>
  <div class="actions"><span class="btn primary disabled">Оплата подключается</span><a class="btn secondary" href="/pro">Назад к тарифам</a></div>
</div></div></section>'''
    return _layout(f'Оплата Clarify {title}', body)


@router.get('/requisites', response_class=HTMLResponse)
async def public_requisites(request: Request):
    seller = {k: html.escape(v) for k, v in _seller().items()}
    incomplete = any(v == 'Не заполнено' for v in seller.values())
    warning = '<div class="notice">Перед отправкой анкеты ЮKassa заполни PUBLIC_SELLER_NAME, PUBLIC_SELLER_INN и PUBLIC_SELLER_EMAIL в переменных окружения Amvera.</div>' if incomplete else ''
    body = f'''
<section><div class="wrap legal"><span class="eyebrow">Юридическая информация</span><h1 style="font-size:clamp(40px,6vw,62px)">Реквизиты</h1>{warning}<div class="table">
<div>Продавец</div><div>{seller['name']}</div>
<div>ИНН</div><div>{seller['inn']}</div>
<div>Email</div><div>{seller['email']}</div>
<div>Поддержка</div><div>{seller['support']}</div>
</div><p>Сервис: Clarify — программный AI-помощник для обработки пользовательских материалов и работы с сохранённой информацией.</p></div></section>'''
    return _layout('Clarify — реквизиты', body)


@router.get('/offer', response_class=HTMLResponse)
async def public_offer(request: Request):
    seller = {k: html.escape(v) for k, v in _seller().items()}
    body = f'''
<section><div class="wrap legal"><span class="eyebrow">Документы</span><h1 style="font-size:clamp(40px,6vw,62px)">Публичная оферта</h1>
<p>Настоящий документ является предложением продавца <b>{seller['name']}</b>, ИНН <b>{seller['inn']}</b>, заключить договор на предоставление доступа к сервису Clarify на изложенных ниже условиях.</p>
<h2>1. Предмет</h2><p>Продавец предоставляет пользователю доступ к цифровому сервису Clarify и выбранному тарифу на оплаченный период. Сервис предназначен для анализа текста, голосовых сообщений, документов, изображений и иных поддерживаемых материалов.</p>
<h2>2. Стоимость и оплата</h2><p>Актуальная стоимость тарифов указана на странице <a href="/pro">/pro</a>. Оплата производится доступными на сайте способами. Обязательство по оплате считается исполненным после подтверждения платёжным провайдером.</p>
<h2>3. Доступ к услуге</h2><p>Доступ активируется после успешного подтверждения платежа и действует в течение периода, указанного при покупке. Технические лимиты конкретного тарифа отображаются до оплаты.</p>
<h2>4. Возвраты</h2><p>Запросы по возврату и ошибочным платежам рассматриваются индивидуально через контакт поддержки. Возврат осуществляется в случаях и порядке, предусмотренных применимым законодательством и правилами платёжного провайдера.</p>
<h2>5. Ограничения</h2><p>Пользователь обязуется не использовать сервис для незаконной деятельности, нарушения прав третьих лиц, атак на инфраструктуру или автоматизированного злоупотребления лимитами.</p>
<h2>6. Контакты</h2><p>Email: <b>{seller['email']}</b>. Поддержка: <b>{seller['support']}</b>.</p>
<p>Оплачивая тариф, пользователь подтверждает, что ознакомился с настоящей офертой и политикой конфиденциальности.</p></div></section>'''
    return _layout('Clarify — публичная оферта', body)


@router.get('/privacy', response_class=HTMLResponse)
async def public_privacy(request: Request):
    seller = {k: html.escape(v) for k, v in _seller().items()}
    body = f'''
<section><div class="wrap legal"><span class="eyebrow">Документы</span><h1 style="font-size:clamp(40px,6vw,62px)">Политика конфиденциальности</h1>
<p>Clarify обрабатывает данные, которые пользователь добровольно передаёт сервису для выполнения запрошенных функций: идентификатор Telegram, текст, файлы, голосовые сообщения, изображения, настройки и технические сведения, необходимые для работы сервиса.</p>
<h2>1. Цели обработки</h2><p>Предоставление функций Clarify, хранение материалов в рамках настроек сервиса, поддержка аккаунта, учёт тарифов и платежей, защита от злоупотреблений и диагностика ошибок.</p>
<h2>2. Платежи</h2><p>Данные банковской карты не хранятся на серверах Clarify. Платёжные данные обрабатываются платёжным провайдером. Clarify получает только технические сведения о статусе и идентификаторе платежа, необходимые для активации тарифа.</p>
<h2>3. Хранение и удаление</h2><p>Пользователь может удалять свои материалы средствами Clarify. Сроки хранения отдельных технических данных могут отличаться, если это требуется для безопасности, расчётов или исполнения юридических обязанностей.</p>
<h2>4. Контакты</h2><p>По вопросам обработки данных: <b>{seller['email']}</b>.</p></div></section>'''
    return _layout('Clarify — политика конфиденциальности', body)
