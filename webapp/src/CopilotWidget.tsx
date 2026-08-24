import { FormEvent, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Bell, Brain, Check, ChevronRight, CircleAlert, Clock3, Crown, Gauge, LoaderCircle,
  Search, ShieldAlert, Sparkles, ThumbsDown, ThumbsUp, Users, WandSparkles, Zap,
} from 'lucide-react'
import { api, haptic, hasTelegramAuth, successHaptic } from './api'

type InboxSignal = {
  kind: 'task' | 'deadline' | 'risk' | 'reminder'
  material_id?: number | null
  title: string
  text: string
  remind_at?: string | null
}
type Inbox = {
  tasks: number
  deadlines: number
  risks: number
  active_reminders: number
  materials_scanned: number
  items: InboxSignal[]
}
type SearchItem = {
  id: number
  type: string
  title: string
  summary: string
  snippet?: string
  score?: number
  created_at?: string | null
}
type SearchResult = { query: string; items: SearchItem[] }
type FullResult = { answer: string; material_id: number; plan: string }
type AdminOverview = {
  users_total: number
  active_24h: number
  materials_total: number
  ai_24h: number
  errors_24h: number
  stars_30d: number
  feedback: { helpful: number; unhelpful: number }
}

const nativeSetInput = (input: HTMLInputElement, value: string) => {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
  descriptor?.set?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

const clickDock = (label: string) => {
  const button = Array.from(document.querySelectorAll('.v1-dock > button')).find(
    item => item.querySelector('small')?.textContent?.trim() === label,
  ) as HTMLButtonElement | undefined
  button?.click()
}

const openInMemory = (query: string) => {
  haptic()
  clickDock('Материалы')
  window.setTimeout(() => {
    const input = document.querySelector('.v1-search input') as HTMLInputElement | null
    if (!input) return
    nativeSetInput(input, query)
    input.focus()
    input.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, 180)
}

const signalIcon = (kind: InboxSignal['kind']) => {
  if (kind === 'deadline') return <Clock3 />
  if (kind === 'risk') return <ShieldAlert />
  if (kind === 'reminder') return <Bell />
  return <Check />
}

function ensureHost(id: string, parent: Element | null, before?: Element | null) {
  if (!parent) return null
  let host = document.getElementById(id)
  if (!host) {
    host = document.createElement('div')
    host.id = id
    if (before && before.parentElement === parent) parent.insertBefore(host, before)
    else parent.appendChild(host)
  }
  return host
}

export default function CopilotWidget() {
  const [homeHost, setHomeHost] = useState<HTMLElement | null>(null)
  const [memoryHost, setMemoryHost] = useState<HTMLElement | null>(null)
  const [detailHost, setDetailHost] = useState<HTMLElement | null>(null)
  const [profileHost, setProfileHost] = useState<HTMLElement | null>(null)
  const [detailTitle, setDetailTitle] = useState('')

  useEffect(() => {
    if (!hasTelegramAuth()) return
    const scan = () => {
      const home = document.querySelector('.v1-stack.home')
      const formats = home?.querySelector('.v1-format-grid') || null
      const next = formats?.nextElementSibling || null
      setHomeHost(ensureHost('clarify-copilot-home', home, next))

      const memory = Array.from(document.querySelectorAll('.v1-stack')).find(
        node => node.querySelector('.v1-page-head h1')?.textContent?.trim() === 'Твои знания',
      ) || null
      const memoryAsk = memory?.querySelector('.v1-memory-ask') || null
      setMemoryHost(ensureHost('clarify-copilot-memory', memory, memoryAsk))

      const detail = document.querySelector('.v1-detail-title')?.closest('.v1-stack') || null
      const actionGrid = detail?.querySelector('.v1-action-grid') || null
      const ask = detail?.querySelector('.v1-ask') || null
      setDetailHost(ensureHost('clarify-copilot-detail', detail, ask))
      setDetailTitle((detail?.querySelector('.v1-detail-title h1')?.textContent || '').trim())
      if (!actionGrid && detailHost) setDetailHost(null)

      const profile = document.querySelector('.v1-profile-card')?.closest('.v1-stack') || null
      const settings = profile?.querySelector('.v1-settings') || null
      setProfileHost(ensureHost('clarify-copilot-profile', profile, settings))
    }
    scan()
    const observer = new MutationObserver(scan)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [detailHost])

  if (!hasTelegramAuth()) return null
  return <>
    {homeHost && createPortal(<InboxCard />, homeHost)}
    {memoryHost && createPortal(<SmartMemorySearch />, memoryHost)}
    {detailHost && detailTitle && createPortal(<MaterialCopilot title={detailTitle} />, detailHost)}
    {profileHost && createPortal(<OwnerOverview />, profileHost)}
  </>
}

function InboxCard() {
  const [data, setData] = useState<Inbox | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    api<Inbox>('/api/copilot/inbox').then(value => { if (alive) setData(value) }).catch(() => undefined).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  if (loading) return <section className="copilot-inbox copilot-loading"><LoaderCircle /><div><b>Важное</b><small>Собираю важное из последних материалов…</small></div></section>
  if (!data || (!data.items.length && !data.active_reminders)) return null

  return <section className="copilot-inbox">
    <header><div><span className="copilot-eyebrow"><Sparkles /> УМНЫЙ ПОМОЩНИК</span><h2>Важное</h2><p>Clarify сам заметил то, что может потребовать внимания.</p></div><span className="copilot-live">АКТИВНО</span></header>
    <div className="copilot-counters">
      <span><Check /><b>{data.tasks}</b><small>задачи</small></span>
      <span><Clock3 /><b>{data.deadlines}</b><small>сроки</small></span>
      <span><ShieldAlert /><b>{data.risks}</b><small>риски</small></span>
    </div>
    {data.items.length > 0 && <div className="copilot-signal-list">{data.items.slice(0, 4).map((item, index) => <button key={`${item.kind}-${item.material_id || 0}-${index}`} onClick={() => item.material_id ? openInMemory(item.title) : undefined} className={item.material_id ? '' : 'static'}>
      <span className={`signal ${item.kind}`}>{signalIcon(item.kind)}</span><div><small>{item.kind === 'task' ? 'ДЕЙСТВИЕ' : item.kind === 'deadline' ? 'СРОК' : item.kind === 'risk' ? 'РИСК' : 'НАПОМИНАНИЕ'}</small><b>{item.title}</b><p>{item.text}</p></div>{item.material_id ? <ChevronRight /> : null}
    </button>)}</div>}
  </section>
}

function SmartMemorySearch() {
  const [q, setQ] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async (event: FormEvent) => {
    event.preventDefault()
    if (q.trim().length < 2) return
    setLoading(true); setError('')
    try {
      setResult(await api<SearchResult>(`/api/copilot/search?q=${encodeURIComponent(q.trim())}&limit=8`))
      successHaptic()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не получилось найти материалы')
    } finally { setLoading(false) }
  }

  return <section className="copilot-search">
    <div className="copilot-search-head"><span><Search /></span><div><small>УМНЫЙ ПОИСК</small><b>Найти по смыслу</b><p>Ищет не только точное название: понимает близкие слова, суммы, сроки и тему.</p></div></div>
    <form onSubmit={run}><Search /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Например: где было про оплату поставщику?"/><button disabled={loading || q.trim().length < 2}>{loading ? <LoaderCircle className="spin" /> : <Sparkles />}</button></form>
    {error && <div className="copilot-error">{error}</div>}
    {result && <div className="copilot-results">{!result.items.length ? <p className="copilot-none">Ничего похожего не нашёл.</p> : result.items.map(item => <button key={item.id} onClick={() => openInMemory(item.title)}><span><Brain /></span><div><b>{item.title}</b><p>{item.snippet || item.summary || 'Материал Clarify'}</p></div><ChevronRight /></button>)}</div>}
  </section>
}

function MaterialCopilot({ title }: { title: string }) {
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [related, setRelated] = useState<SearchItem[]>([])
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [rated, setRated] = useState<boolean | null>(null)

  useEffect(() => {
    let alive = true
    setMaterialId(null); setRelated([]); setAnswer(''); setError(''); setRated(null)
    api<SearchResult>(`/api/copilot/search?q=${encodeURIComponent(title)}&limit=5`).then(async data => {
      if (!alive) return
      const exact = data.items.find(item => item.title.trim() === title.trim()) || data.items[0]
      if (!exact) return
      setMaterialId(exact.id)
      try {
        const rel = await api<{ items: SearchItem[] }>(`/api/copilot/materials/${exact.id}/related`)
        if (alive) setRelated(rel.items)
      } catch { /* related materials are optional */ }
    }).catch(() => undefined)
    return () => { alive = false }
  }, [title])

  const full = async () => {
    if (!materialId) return
    haptic('medium'); setLoading(true); setError(''); setAnswer('')
    try {
      const result = await api<FullResult>(`/api/copilot/materials/${materialId}/full`, { method: 'POST' })
      setAnswer(result.answer); successHaptic()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не получилось сделать полный разбор')
    } finally { setLoading(false) }
  }

  const feedback = async (positive: boolean) => {
    if (rated !== null) return
    setRated(positive)
    try { await api('/api/copilot/feedback', { method: 'POST', body: JSON.stringify({ positive, feature: 'full', material_id: materialId }) }); successHaptic() } catch { /* feedback is non-critical */ }
  }

  const needsPro = error.includes('PRO')
  return <section className="material-copilot">
    <button className="copilot-full-button" disabled={!materialId || loading} onClick={() => void full()}><span><WandSparkles /></span><div><b>{loading ? 'Делаю полный разбор…' : '⚡ Сделать всё'}</b><small>Главное + действия + сроки + деньги + риски одним запросом</small></div>{loading ? <LoaderCircle className="spin" /> : <ChevronRight />}</button>
    {error && <div className="copilot-full-error"><CircleAlert /><div><b>Не получилось</b><p>{error}</p>{needsPro && <button onClick={() => window.dispatchEvent(new Event('clarify:open-plans'))}>Открыть тарифы</button>}</div></div>}
    {answer && <div className="copilot-full-answer"><span className="copilot-eyebrow"><Sparkles /> ПОЛНЫЙ РАЗБОР</span><pre>{answer}</pre><div className="copilot-feedback"><small>Полезный разбор?</small><button className={rated === true ? 'active' : ''} onClick={() => void feedback(true)}><ThumbsUp /></button><button className={rated === false ? 'active bad' : ''} onClick={() => void feedback(false)}><ThumbsDown /></button></div></div>}
    {related.length > 0 && <div className="copilot-related"><span>Связанные материалы</span>{related.slice(0, 3).map(item => <button key={item.id} onClick={() => openInMemory(item.title)}><Brain /><div><b>{item.title}</b><small>{item.snippet || item.summary}</small></div><ChevronRight /></button>)}</div>}
  </section>
}

function OwnerOverview() {
  const [data, setData] = useState<AdminOverview | null>(null)
  useEffect(() => {
    let alive = true
    api<AdminOverview>('/api/copilot/admin/overview').then(value => { if (alive) setData(value) }).catch(() => undefined)
    return () => { alive = false }
  }, [])
  const satisfaction = useMemo(() => {
    if (!data) return null
    const total = data.feedback.helpful + data.feedback.unhelpful
    return total ? Math.round(data.feedback.helpful / total * 100) : null
  }, [data])
  if (!data) return null
  return <section className="copilot-admin">
    <div className="copilot-search-head"><span><Crown /></span><div><small>АНАЛИТИКА ВЛАДЕЛЬЦА</small><b>Clarify сегодня</b><p>Короткая панель владельца без отдельной админки.</p></div></div>
    <div className="copilot-admin-grid">
      <span><Users /><small>Активны 24 ч</small><b>{data.active_24h}</b><em>из {data.users_total}</em></span>
      <span><Sparkles /><small>ИИ за 24 ч</small><b>{data.ai_24h}</b></span>
      <span><Gauge /><small>Материалов</small><b>{data.materials_total}</b></span>
      <span className={data.errors_24h ? 'warn' : ''}><CircleAlert /><small>Ошибок 24 ч</small><b>{data.errors_24h}</b></span>
      <span><Zap /><small>Stars / 30 дн.</small><b>{data.stars_30d}</b></span>
      <span><ThumbsUp /><small>Полезность</small><b>{satisfaction === null ? '—' : `${satisfaction}%`}</b></span>
    </div>
  </section>
}
