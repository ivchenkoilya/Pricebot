import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Crown, Gem, LoaderCircle, PlusCircle, Sparkles, X, Zap } from 'lucide-react'
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

export default function PlansWidget() {
  const [dock, setDock] = useState<HTMLElement | null>(null)
  const [open, setOpen] = useState(false)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loading, setLoading] = useState(false)
  const [buying, setBuying] = useState('')
  const [error, setError] = useState('')

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
    setBuying(product); setError('')
    try {
      const result = await api<{ invoice_url: string }>('/api/plans/invoice', { method: 'POST', body: JSON.stringify({ product }) })
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
      <header className="plans-header"><div><span>CLARIFY PLANS</span><h1>Выбери свой Clarify</h1><p>Плати за больше возможностей, а не за непонятные токены.</p></div><button onClick={() => setOpen(false)} aria-label="Закрыть"><X /></button></header>

      {catalog && <div className="plans-current"><div><small>ТЕКУЩИЙ ДОСТУП</small><b>{catalog.current === 'MAX' ? 'PRO MAX' : catalog.current}</b></div><div><small>ДОП. ЗАПРОСЫ</small><b>{catalog.current === 'OWNER' ? '∞' : catalog.bonus_requests}</b></div></div>}
      {loading && !catalog && <div className="plans-loading"><LoaderCircle /><span>Загружаю тарифы…</span></div>}
      {error && <div className="plans-error">{error}</div>}

      {catalog?.current === 'OWNER' && <section className="plans-owner"><Crown /><div><small>OWNER</small><h2>Unlimited включён</h2><p>Для владельца Clarify клиентские лимиты отключены.</p></div></section>}

      {catalog && <div className="plans-grid">{catalog.plans.map(plan => {
        const product = plan.code === 'MAX' ? 'max' : plan.code.toLowerCase()
        const active = catalog.current === plan.code
        const paid = plan.price > 0
        return <section key={plan.code} className={`plan-card ${plan.code.toLowerCase()} ${active ? 'active' : ''}`}>
          <div className="plan-card-top"><span className="plan-icon">{plan.code === 'MAX' ? <Gem /> : plan.code === 'PRO' ? <Crown /> : <Sparkles />}</span><div><small>{plan.tagline}</small><h2>{plan.title}</h2></div>{active && <em><Check /> Сейчас</em>}</div>
          <div className="plan-price">{paid ? <><b>{plan.price}</b><span>⭐ / {plan.period}</span></> : <><b>0</b><span>⭐ навсегда</span></>}</div>
          <div className="plan-reason">{plan.code === 'FREE' ? 'Попробовать Clarify без оплаты.' : plan.code === 'PRO' ? 'Для ежедневной работы, учёбы и длинных материалов.' : 'Когда Clarify используется много и 300 запросов в день уже мало.'}</div>
          <ul>{plan.features.map(feature => <li key={feature}><Check />{feature}</li>)}</ul>
          {paid && catalog.current !== 'OWNER' && <button className="plan-buy" disabled={active || buying === product} onClick={() => void buy(product)}>{buying === product ? <LoaderCircle className="spin" /> : <Zap />}{active ? 'Тариф активен' : `Подключить за ${plan.price} ⭐`}</button>}
        </section>
      })}</div>}

      {catalog && catalog.current !== 'OWNER' && <section className="packs-section"><div className="packs-head"><span><PlusCircle /></span><div><small>НЕ НУЖНА ПОДПИСКА?</small><h2>Докупить запросы</h2><p>{catalog.note}</p></div></div><div className="packs-grid">{catalog.packs.map(pack => <button key={pack.product} disabled={buying === pack.product} onClick={() => void buy(pack.product)}><div><b>{pack.title}</b><small>Останутся на аккаунте</small></div><strong>{pack.price} ⭐</strong></button>)}</div></section>}

      <section className="plans-why"><span><Sparkles /></span><div><h3>Почему платить за PRO?</h3><p>FREE остаётся рабочим. PRO снимает ограничения, открывает Smart AI и позволяет разбирать длинные голосовые и документы без постоянных остановок по лимиту.</p></div></section>
    </div></div>}
  </>
}
