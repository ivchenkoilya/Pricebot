import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Coins, Crown, Gem, LoaderCircle, PlusCircle, Sparkles, X, Zap } from 'lucide-react'
import { api, haptic, hasTelegramAuth, openInvoice, successHaptic } from './api'

type Plan = {
  code: 'FREE' | 'PRO' | 'MAX'
  title: string
  price: number
  period: string
  daily_requests: number
  voice_minutes: number
  document_pages: number
  tagline: string
  features: string[]
}

type Pack = { product: string; requests: number; price: number; title: string }
type Catalog = {
  current: 'FREE' | 'PRO' | 'MAX' | 'OWNER'
  pro_until?: string | null
  bonus_requests: number
  plans: Plan[]
  packs: Pack[]
  note: string
}

const packCopy = (requests: number) => {
  if (requests >= 2000) return {
    badge: 'МАКСИМАЛЬНЫЙ ЗАПАС',
    title: 'Для больших проектов',
    text: 'Подойдёт, если Clarify используется каждый день для документов, Memory, сравнений и длинных рабочих диалогов.',
  }
  if (requests >= 500) return {
    badge: 'ПОПУЛЯРНЫЙ ПАКЕТ',
    title: 'Для активной недели',
    text: 'Хороший запас без перехода на более дорогую подписку. Запросы остаются на аккаунте, пока не закончатся.',
  }
  return {
    badge: 'БЫСТРЫЙ ЗАПАС',
    title: 'Когда немного не хватило',
    text: 'Небольшой пакет на случай, если дневной лимит закончился, а работу нужно продолжить прямо сейчас.',
  }
}

export default function PlansWidget() {
  const [dock, setDock] = useState<HTMLElement | null>(null)
  const [open, setOpen] = useState(false)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loading, setLoading] = useState(false)
  const [buying, setBuying] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<Catalog>('/api/plans')
      setCatalog(data)
      document.body.dataset.clarifyPlan = data.current
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить тарифы')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!hasTelegramAuth()) return
    const find = () => setDock(document.querySelector('.v1-dock') as HTMLElement | null)
    find(); void load()
    const observer = new MutationObserver(find)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [load])

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!open || !tg?.BackButton) return
    const close = () => setOpen(false)
    tg.BackButton.show(); tg.BackButton.onClick(close)
    return () => {
      tg.BackButton?.offClick(close)
      const active = document.querySelector('.v1-dock button.active small')?.textContent?.trim()
      if (active === 'Главная') tg.BackButton?.hide(); else tg.BackButton?.show()
    }
  }, [open])

  if (!hasTelegramAuth()) return null

  const buy = async (product: string) => {
    setNotice(''); setError('')

    // OWNER should still see the exact commercial storefront. We intentionally
    // do not create a paid subscription invoice for the owner account because
    // its access is already unlimited. Customer accounts use the same buttons
    // and receive the real Telegram Stars invoice below.
    if (catalog?.current === 'OWNER' && (product === 'pro' || product === 'max')) {
      haptic('medium')
      setNotice('Режим OWNER: у обычного пользователя эта кнопка сразу открывает официальный счёт Telegram Stars. На аккаунте владельца тариф уже Unlimited, поэтому повторно списывать Stars не нужно.')
      return
    }

    setBuying(product)
    try {
      const result = await api<{ invoice_url: string }>('/api/plans/invoice', {
        method: 'POST', body: JSON.stringify({ product }),
      })
      openInvoice(result.invoice_url, () => {
        successHaptic(); window.setTimeout(() => void load(), 900)
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось открыть оплату')
    } finally {
      setBuying('')
    }
  }

  const tab = dock ? createPortal(
    <button className={open ? 'plans-tab active' : 'plans-tab'} onClick={() => { haptic(); setOpen(true); void load() }}>
      <span><Gem /></span><small>Тарифы</small><i />
    </button>, dock,
  ) : null

  return <>
    {tab}
    {open && <div className="plans-overlay"><div className="plans-page">
      <header className="plans-header"><div><span>CLARIFY PLANS</span><h1>Выбери свой Clarify</h1><p>Понятные лимиты, официальная оплата через Telegram Stars и возможность докупить запросы без смены тарифа.</p></div><button onClick={() => setOpen(false)} aria-label="Закрыть"><X /></button></header>

      {catalog && <div className="plans-current"><div><small>ТЕКУЩИЙ ДОСТУП</small><b>{catalog.current === 'MAX' ? 'PRO MAX' : catalog.current}</b></div><div><small>ДОП. ЗАПРОСЫ</small><b>{catalog.current === 'OWNER' ? '∞' : catalog.bonus_requests}</b></div></div>}
      {loading && !catalog && <div className="plans-loading"><LoaderCircle /><span>Загружаю тарифы…</span></div>}
      {error && <div className="plans-error">{error}</div>}
      {notice && <div className="plans-notice">{notice}</div>}

      {catalog?.current === 'OWNER' && <section className="plans-owner"><Crown /><div><small>OWNER · ВИТРИНА ВКЛЮЧЕНА</small><h2>Unlimited включён</h2><p>Ниже ты видишь тарифы и кнопки так же, как их видит обычный пользователь. Тарифные кнопки на OWNER работают как предпросмотр и не списывают Stars.</p></div></section>}

      {catalog && <div className="plans-grid">{catalog.plans.map(plan => {
        const product = plan.code === 'MAX' ? 'max' : plan.code.toLowerCase()
        const active = catalog.current === plan.code
        const paid = plan.price > 0
        return <section key={plan.code} className={`plan-card ${plan.code.toLowerCase()} ${active ? 'active' : ''}`}>
          <div className="plan-card-top"><span className="plan-icon">{plan.code === 'MAX' ? <Gem /> : plan.code === 'PRO' ? <Crown /> : <Sparkles />}</span><div><small>{plan.tagline}</small><h2>{plan.title}</h2></div>{active && <em><Check /> Сейчас</em>}</div>
          <div className="plan-price">{paid ? <><b>{plan.price}</b><span>⭐ / {plan.period}</span></> : <><b>0</b><span>⭐ навсегда</span></>}</div>
          <div className="plan-reason">{plan.code === 'FREE' ? 'Полноценный старт: попробовать Clarify без оплаты и понять, насколько он экономит время.' : plan.code === 'PRO' ? 'Для ежедневной работы, учёбы и длинных материалов без постоянной остановки на бесплатном лимите.' : 'Для активного использования: большой пул запросов, Smart AI и максимум доступной работы в течение дня.'}</div>
          <ul>{plan.features.map(feature => <li key={feature}><Check />{feature}</li>)}</ul>
          {paid && <button className="plan-buy" disabled={active || buying === product} onClick={() => void buy(product)}>{buying === product ? <LoaderCircle className="spin" /> : <Zap />}{active ? 'Тариф уже активен' : `Подключить за ${plan.price} ⭐`}</button>}
          {!paid && <div className="plan-free-label"><Check /> Бесплатный тариф доступен всем</div>}
        </section>
      })}</div>}

      {catalog && <section className="request-explainer">
        <span><Coins /></span>
        <div><small>ЧТО ТАКОЕ AI-ЗАПРОС?</small><h2>Один запрос = одно действие Clarify</h2><p>Например: разобрать текст, ответить на вопрос по материалу, сделать пересказ, найти риски, переписать сообщение или выполнить другое AI-действие. Пакет запросов нужен, если дневной лимит закончился, но подписку менять не хочется.</p></div>
      </section>}

      {catalog && <section className="packs-section">
        <div className="packs-head"><span><PlusCircle /></span><div><small>БЕЗ ПОДПИСКИ ИЛИ СВЕРХ ЛИМИТА</small><h2>Докупить отдельные запросы</h2><p>{catalog.note} Они не сгорают ночью и остаются на аккаунте до использования.</p></div></div>
        <div className="packs-grid">{catalog.packs.map(pack => {
          const copy = packCopy(pack.requests)
          return <article className="pack-card" key={pack.product}>
            <div className="pack-card-copy"><small>{copy.badge}</small><div className="pack-amount">+{pack.requests}</div><h3>{copy.title}</h3><p>{copy.text}</p></div>
            <div className="pack-card-bottom"><div><strong>{pack.price} ⭐</strong><small>разовая покупка</small></div><button disabled={buying === pack.product} onClick={() => void buy(pack.product)}>{buying === pack.product ? <LoaderCircle className="spin" /> : <Zap />}Купить</button></div>
          </article>
        })}</div>
      </section>}

      <section className="plans-why"><span><Sparkles /></span><div><h3>Почему платить за PRO?</h3><p>FREE остаётся рабочим. PRO нужен не ради красивого значка: он увеличивает дневной объём работы, открывает Smart AI и позволяет дольше работать с голосовыми и большими документами. Если подписка не нужна — можно просто докупить запросы.</p></div></section>
    </div></div>}
  </>
}
