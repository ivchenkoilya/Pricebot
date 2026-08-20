import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { api, apiForm, haptic, hasTelegramAuth, Material, Me, openInvoice, successHaptic } from './api'

type Page = 'home' | 'materials' | 'projects' | 'profile' | 'material' | 'project' | 'compare' | 'reminders' | 'compose' | 'pro'
type IntakeKind = 'text' | 'link' | 'image' | 'document' | 'audio'
type Project = { id: number; name: string; count: number; created_at?: string | null; materials?: Material[] }
type Reminder = { id: number; text: string; remind_at: string; status: string }
type Source = { title: string; page?: number; id?: number; type?: string }
type Answer = { answer: string; sources?: Source[] }
type Stats = { materials: number; projects: number; reminders: number; ai_today: number }

type Common = {
  me: Me
  setPage: (p: Page) => void
  setError: (s: string) => void
  busy: boolean
  setBusy: (b: boolean) => void
}

const typeIcon = (type: string) => {
  if (['voice', 'audio'].includes(type)) return '🎤'
  if (['image', 'screenshot'].includes(type)) return '🖼'
  if (['link', 'video', 'video_link'].includes(type)) return '🔗'
  if (['pdf', 'docx', 'document', 'text'].includes(type)) return type === 'text' ? '✍️' : '📄'
  if (['xlsx', 'csv', 'spreadsheet'].includes(type)) return '📊'
  if (type === 'forwarded') return '💬'
  return '📝'
}

const prettyType = (type: string) => ({
  voice: 'Голос', audio: 'Аудио', image: 'Изображение', screenshot: 'Скриншот', link: 'Ссылка',
  video: 'Видео', video_link: 'Видео', pdf: 'PDF', docx: 'DOCX', document: 'Документ', spreadsheet: 'Таблица',
  xlsx: 'XLSX', csv: 'CSV', forwarded: 'Сообщение', draft: 'Черновик', text: 'Текст',
}[type] || type)

const formatDate = (value?: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function Loading({ text = 'Загружаю…' }: { text?: string }) {
  return <div className="loading-card"><div className="ai-orb"><span>✦</span></div><div><b>{text}</b><small>Clarify уже работает</small></div></div>
}

function Empty({ title, text, action }: { title: string; text: string; action?: () => void }) {
  return <div className="empty"><div className="empty-icon">✦</div><h3>{title}</h3><p>{text}</p>{action && <button className="primary" onClick={action}>＋ Добавить материал</button>}</div>
}

function Sources({ items = [] }: { items?: Source[] }) {
  if (!items.length) return null
  return <div className="sources"><span>Источники</span>{items.map((s, i) => <div key={`${s.title}-${s.page || 0}-${i}`}>↗ {s.title}{s.page ? ` · стр. ${s.page}` : ''}</div>)}</div>
}

function App() {
  const tg = window.Telegram?.WebApp
  const [page, setPage] = useState<Page>('home')
  const [me, setMe] = useState<Me | null>(null)
  const [globalError, setGlobalError] = useState('')
  const [busy, setBusy] = useState(false)
  const [materials, setMaterials] = useState<Material[]>([])
  const [selectedMaterial, setSelectedMaterial] = useState<Material | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [intakeOpen, setIntakeOpen] = useState(false)
  const [intakeKind, setIntakeKind] = useState<IntakeKind | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(() => window.localStorage.getItem('clarify_onboarding_v2') !== 'done')

  useEffect(() => {
    tg?.ready()
    tg?.expand()
    tg?.setHeaderColor?.('#061126')
    tg?.setBackgroundColor?.('#061126')
  }, [tg])

  const refreshMe = useCallback(async () => {
    try {
      const value = await api<Me>('/api/me')
      setMe(value)
      setGlobalError('')
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Не удалось открыть Clarify')
    }
  }, [])

  useEffect(() => { if (hasTelegramAuth()) void refreshMe() }, [refreshMe])

  useEffect(() => {
    if (!tg?.BackButton) return
    const handler = () => {
      if (intakeOpen) {
        setIntakeOpen(false)
        setIntakeKind(null)
        return
      }
      if (['material', 'project'].includes(page)) setPage(page === 'material' ? 'materials' : 'projects')
      else if (page !== 'home') setPage('home')
      else tg.close?.()
    }
    if (page !== 'home' || intakeOpen) tg.BackButton.show(); else tg.BackButton.hide()
    tg.BackButton.onClick(handler)
    return () => tg.BackButton?.offClick(handler)
  }, [page, tg, intakeOpen])

  const navigate = (next: Page) => {
    haptic()
    setGlobalError('')
    setIntakeOpen(false)
    setIntakeKind(null)
    setPage(next)
  }

  const openIntake = (kind: IntakeKind | null = null) => {
    haptic('medium')
    setIntakeKind(kind)
    setIntakeOpen(true)
  }

  const openMaterial = async (id: number) => {
    setBusy(true)
    try {
      const item = await api<Material>(`/api/materials/${id}`)
      setSelectedMaterial(item)
      setPage('material')
    } catch (e) {
      setGlobalError(e instanceof Error ? e.message : 'Не удалось открыть материал')
    } finally {
      setBusy(false)
    }
  }

  const intakeDone = (item: Material) => {
    successHaptic()
    setIntakeOpen(false)
    setIntakeKind(null)
    setSelectedMaterial(item)
    setMaterials(current => [item, ...current.filter(x => x.id !== item.id)])
    setPage('material')
  }

  if (!hasTelegramAuth()) {
    return <main className="outside">
      <img className="outside-banner" src="/assets/clarify-banner.webp" alt="Clarify" />
      <div className="glass"><span className="eyebrow">TELEGRAM MINI APP</span><h1>Clarify</h1><p>Открой приложение кнопкой «🚀 Открыть Clarify» внутри бота.</p></div>
    </main>
  }

  if (!me && !globalError) return <main className="app-shell boot"><Loading text="Открываю AI Workspace…" /></main>
  if (!me) return <main className="outside"><div className="glass"><h2>Не получилось открыть Clarify</h2><p>{globalError}</p><button className="primary" onClick={() => void refreshMe()}>Попробовать снова</button></div></main>

  const common = { me, setPage: navigate, setError: setGlobalError, busy, setBusy }

  return <div className="app-shell">
    <div className="ambient ambient-a" /><div className="ambient ambient-b" /><div className="noise" />

    <header className="topbar">
      <button className="brand" onClick={() => navigate('home')}>
        <div className="brand-mark">✦</div>
        <div><strong>Clarify</strong><span>AI Workspace</span></div>
      </button>
      <button className={`plan-pill ${me.owner ? 'owner' : ''}`} onClick={() => navigate(me.owner ? 'profile' : 'pro')}>
        {me.owner ? '👑 OWNER' : me.plan === 'PRO' ? '✦ PRO' : 'FREE'}
      </button>
    </header>

    {globalError && <div className="toast error" onClick={() => setGlobalError('')}><div><b>Не получилось</b><span>{globalError}</span></div><strong>×</strong></div>}

    <section className="page">
      {page === 'home' && <Home {...common} onAdd={openIntake} openMaterial={openMaterial} />}
      {page === 'materials' && <Materials {...common} items={materials} setItems={setMaterials} open={openMaterial} onAdd={openIntake} />}
      {page === 'material' && selectedMaterial && <MaterialDetail {...common} material={selectedMaterial} onDeleted={() => { setSelectedMaterial(null); setPage('materials') }} />}
      {page === 'projects' && <Projects {...common} items={projects} setItems={setProjects} open={async id => {
        setBusy(true)
        try { const item = await api<Project>(`/api/projects/${id}`); setSelectedProject(item); setPage('project') }
        catch (e) { setGlobalError(e instanceof Error ? e.message : 'Не удалось открыть проект') }
        finally { setBusy(false) }
      }} />}
      {page === 'project' && selectedProject && <ProjectDetail {...common} project={selectedProject} />}
      {page === 'compare' && <Compare {...common} />}
      {page === 'reminders' && <Reminders {...common} />}
      {page === 'compose' && <Compose {...common} />}
      {page === 'pro' && <Pro {...common} refreshMe={refreshMe} />}
      {page === 'profile' && <Profile {...common} refreshMe={refreshMe} />}
    </section>

    <nav className="bottom-nav">
      <button className={page === 'home' ? 'active' : ''} onClick={() => navigate('home')}><span>⌂</span><small>Главная</small></button>
      <button className={page === 'materials' || page === 'material' ? 'active' : ''} onClick={() => navigate('materials')}><span>◈</span><small>Memory</small></button>
      <button className="nav-add" onClick={() => openIntake()} aria-label="Добавить материал"><span>＋</span></button>
      <button className={page === 'compose' ? 'active' : ''} onClick={() => navigate('compose')}><span>✦</span><small>AI</small></button>
      <button className={page === 'profile' || page === 'pro' ? 'active' : ''} onClick={() => navigate('profile')}><span>◎</span><small>Профиль</small></button>
    </nav>

    <IntakeSheet open={intakeOpen} kind={intakeKind} onKind={setIntakeKind} onClose={() => { if (!busy) { setIntakeOpen(false); setIntakeKind(null) } }} onDone={intakeDone} setError={setGlobalError} />
    {showOnboarding && <Onboarding onDone={() => { window.localStorage.setItem('clarify_onboarding_v2', 'done'); setShowOnboarding(false) }} />}
  </div>
}

function Home({ me, setPage, onAdd, openMaterial }: Common & { onAdd: (kind?: IntakeKind | null) => void; openMaterial: (id: number) => Promise<void> }) {
  const [recent, setRecent] = useState<Material[]>([])
  useEffect(() => { void api<{ items: Material[] }>('/api/materials?limit=3').then(d => setRecent(d.items)).catch(() => undefined) }, [])

  return <div className="stack home-stack">
    <section className="hero premium-card">
      <div className="hero-media"><img src="/assets/clarify-banner.webp" alt="Clarify — Send anything. Get clarity." /></div>
      <div className="hero-copy">
        <span className="eyebrow">AI INBOX · TELEGRAM</span>
        <h1>Что разберём<br />сегодня?</h1>
        <p>Отправь всё, на что не хочется тратить время. Clarify превратит входящий хаос в ясный результат.</p>
        <button className="primary wide hero-cta" onClick={() => onAdd()}>＋ <span>Добавить материал</span><i>⌁</i></button>
      </div>
    </section>

    <div className="format-row">
      <button onClick={() => onAdd('audio')}>🎤 <span>Голос</span></button>
      <button onClick={() => onAdd('document')}>📄 <span>Документ</span></button>
      <button onClick={() => onAdd('image')}>🖼 <span>Скрин</span></button>
      <button onClick={() => onAdd('link')}>🔗 <span>Ссылка</span></button>
      <button onClick={() => onAdd('text')}>✍️ <span>Текст</span></button>
    </div>

    {recent.length > 0 && <section className="continue-block">
      <div className="section-row"><div><span className="eyebrow">CONTINUE</span><h2>Продолжить</h2></div><button className="text-btn" onClick={() => setPage('materials')}>Все →</button></div>
      <div className="recent-strip">{recent.map(item => <button className="recent-card" key={item.id} onClick={() => void openMaterial(item.id)}><span>{typeIcon(item.type)}</span><div><small>{prettyType(item.type)} · {formatDate(item.created_at)}</small><b>{item.title}</b><p>{item.summary || 'Открыть материал'}</p></div></button>)}</div>
    </section>}

    <section>
      <div className="section-row"><div><span className="eyebrow">QUICK ACTIONS</span><h2>Быстрые действия</h2></div></div>
      <div className="quick-grid">
        <Quick icon="🧠" title="Memory" text="Поиск по знаниям" onClick={() => setPage('materials')} />
        <Quick icon="📁" title="Проекты" text="Материалы по теме" onClick={() => setPage('projects')} />
        <Quick icon="🔀" title="Сравнить" text="Два документа" onClick={() => setPage('compare')} />
        <Quick icon="⏰" title="Напомнить" text="Не забыть важное" onClick={() => setPage('reminders')} />
        <Quick icon="✍️" title="Написать" text="Ответ в твоём стиле" onClick={() => setPage('compose')} />
        <Quick icon={me.owner ? '👑' : '⚡'} title={me.owner ? 'OWNER' : 'Clarify PRO'} text={me.owner ? 'Unlimited access' : 'Больше возможностей'} onClick={() => setPage(me.owner ? 'profile' : 'pro')} />
      </div>
    </section>

    <div className="insight-card"><div className="spark">✦</div><div><span className="eyebrow">CLARIFY TIP</span><b>Не придумывай идеальный промпт.</b><p>Просто добавь материал. Clarify сам поймёт формат и предложит полезные действия.</p></div></div>
  </div>
}

function Quick({ icon, title, text, onClick }: { icon: string; title: string; text: string; onClick: () => void }) {
  return <button className="quick" onClick={() => { haptic(); onClick() }}><span className="quick-icon">{icon}</span><div><b>{title}</b><small>{text}</small></div><i>↗</i></button>
}

function IntakeSheet({ open, kind, onKind, onClose, onDone, setError }: {
  open: boolean
  kind: IntakeKind | null
  onKind: (kind: IntakeKind | null) => void
  onClose: () => void
  onDone: (item: Material) => void
  setError: (value: string) => void
}) {
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { setText(''); setUrl(''); setFile(null) }, [kind, open])
  if (!open) return null

  const options: { id: IntakeKind; icon: string; title: string; text: string }[] = [
    { id: 'audio', icon: '🎤', title: 'Голос / аудио', text: 'Расшифрую и найду смысл' },
    { id: 'document', icon: '📄', title: 'Документ', text: 'PDF, DOCX, TXT, XLSX' },
    { id: 'image', icon: '🖼', title: 'Фото / скрин', text: 'Прочитаю и объясню' },
    { id: 'link', icon: '🔗', title: 'Ссылка', text: 'Страница или видео' },
    { id: 'text', icon: '✍️', title: 'Текст', text: 'Вставь сообщение или заметку' },
  ]

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!kind) return
    setBusy(true)
    setError('')
    try {
      let item: Material
      if (kind === 'text') {
        if (!text.trim()) return
        item = await api<Material>('/api/intake/text', { method: 'POST', body: JSON.stringify({ text: text.trim() }) })
      } else if (kind === 'link') {
        if (!url.trim()) return
        item = await api<Material>('/api/intake/link', { method: 'POST', body: JSON.stringify({ url: url.trim() }) })
      } else {
        if (!file) return
        const form = new FormData()
        form.append('file', file)
        item = await apiForm<Material>('/api/intake/file', form)
      }
      onDone(item)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не получилось обработать материал')
    } finally {
      setBusy(false)
    }
  }

  const accept = kind === 'image' ? 'image/*' : kind === 'audio' ? 'audio/*,.ogg,.opus,.m4a,.mp3,.wav,.webm' : '.pdf,.docx,.txt,.md,.xlsx,.csv'
  const title = options.find(x => x.id === kind)?.title || 'Добавить материал'

  return <div className="sheet-backdrop" onMouseDown={e => { if (e.currentTarget === e.target && !busy) onClose() }}>
    <div className="sheet">
      <div className="sheet-handle" />
      <div className="sheet-head"><div><span className="eyebrow">ADD TO CLARIFY</span><h2>{kind ? title : 'Что хочешь разобрать?'}</h2></div><button className="sheet-close" onClick={onClose} disabled={busy}>×</button></div>

      {busy ? <Processing /> : !kind ? <div className="intake-grid">{options.map(option => <button key={option.id} onClick={() => onKind(option.id)}><span>{option.icon}</span><div><b>{option.title}</b><small>{option.text}</small></div><i>›</i></button>)}</div> : <form className="intake-form" onSubmit={submit}>
        <button type="button" className="back-link" onClick={() => onKind(null)}>← Другой тип</button>
        {kind === 'text' && <textarea autoFocus rows={8} value={text} onChange={e => setText(e.target.value)} placeholder="Вставь сообщение, заметку, переписку или любой текст…" />}
        {kind === 'link' && <><input autoFocus value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…" /><div className="hint">Подойдут обычные публичные страницы, YouTube, Shorts и другие поддерживаемые ссылки.</div></>}
        {['image', 'document', 'audio'].includes(kind) && <label className={`file-drop ${file ? 'selected' : ''}`}>
          <input type="file" accept={accept} onChange={e => setFile(e.target.files?.[0] || null)} />
          <span>{kind === 'image' ? '🖼' : kind === 'audio' ? '🎤' : '📄'}</span>
          <b>{file ? file.name : 'Выбрать файл'}</b>
          <small>{file ? `${Math.max(0.01, file.size / 1024 / 1024).toFixed(1)} МБ` : 'Нажми здесь — файл загрузится прямо в Clarify'}</small>
        </label>}
        <button className="primary wide" disabled={(kind === 'text' && !text.trim()) || (kind === 'link' && !url.trim()) || (['image', 'document', 'audio'].includes(kind) && !file)}>
          ✦ Разобрать материал
        </button>
      </form>}
    </div>
  </div>
}

function Processing() {
  return <div className="processing">
    <div className="processing-orb"><span>✦</span></div>
    <h3>Clarify думает…</h3><p>Обычно это занимает несколько секунд.</p>
    <div className="process-steps"><div className="done"><span>✓</span>Получаю материал</div><div className="done"><span>✓</span>Определяю формат</div><div className="active"><span>✦</span>Понимаю содержание</div><div><span>○</span>Формирую результат</div></div>
  </div>
}

function Materials({ items, setItems, open, setError, onAdd }: Common & { items: Material[]; setItems: (v: Material[]) => void; open: (id: number) => Promise<void>; onAdd: (kind?: IntakeKind | null) => void }) {
  const [q, setQ] = useState('')
  const [type, setType] = useState('all')
  const [loading, setLoading] = useState(false)
  const [memoryQuestion, setMemoryQuestion] = useState('')
  const [memoryAnswer, setMemoryAnswer] = useState<Answer | null>(null)
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        const params = new URLSearchParams({ limit: '30', type })
        if (q.trim()) params.set('q', q.trim())
        const data = await api<{ items: Material[] }>(`/api/materials?${params}`)
        setItems(data.items)
      } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить Memory') }
      finally { setLoading(false) }
    }, 220)
    return () => window.clearTimeout(timer)
  }, [q, type, setItems, setError])

  const askMemory = async (e: FormEvent) => {
    e.preventDefault(); if (!memoryQuestion.trim()) return
    setAsking(true); setMemoryAnswer(null)
    try {
      setMemoryAnswer(await api<Answer>('/api/memory/ask', { method: 'POST', body: JSON.stringify({ question: memoryQuestion.trim() }) }))
      successHaptic()
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось спросить Memory') }
    finally { setAsking(false) }
  }

  return <div className="stack">
    <div className="page-head"><div><span className="eyebrow">CLARIFY MEMORY</span><h1>Твои знания</h1><p>Всё, что ты уже отправлял Clarify.</p></div><button className="icon-btn" onClick={() => onAdd()}>＋</button></div>

    <form className="memory-ask premium-card" onSubmit={askMemory}>
      <div className="memory-icon">✦</div><div className="memory-input"><label>Спросить мои материалы</label><input value={memoryQuestion} onChange={e => setMemoryQuestion(e.target.value)} placeholder="Что я изучал про маркетинг?" /></div><button disabled={asking || !memoryQuestion.trim()}>{asking ? '…' : '↑'}</button>
    </form>
    {asking && <Loading text="Ищу по Memory…" />}
    {memoryAnswer && <div className="answer-card memory-result"><span className="eyebrow">MEMORY ANSWER</span><div className="answer-text">{memoryAnswer.answer}</div><Sources items={memoryAnswer.sources} /></div>}

    <div className="search"><span>⌕</span><input value={q} onChange={e => setQ(e.target.value)} placeholder="Фильтр по названию и содержимому…" /></div>
    <div className="chips">{[['all','Все'],['documents','Документы'],['voice','Голос'],['images','Фото'],['links','Ссылки'],['text','Текст']].map(([id,label]) => <button key={id} className={type===id?'active':''} onClick={() => setType(id)}>{label}</button>)}</div>

    {loading ? <Loading text="Открываю Memory…" /> : !items.length ? <Empty title="Твоя Memory пока пустая" text="Добавь первый материал — Clarify начнёт собирать твою личную базу знаний." action={() => onAdd()} /> : <div className="material-list">{items.map(item => <button className="material-card" key={item.id} onClick={() => void open(item.id)}><div className="material-icon">{typeIcon(item.type)}</div><div className="material-body"><div className="material-meta"><span>{prettyType(item.type)}</span><time>{formatDate(item.created_at)}</time></div><b>{item.title}</b><p>{item.summary || 'Материал сохранён. Открой, чтобы спросить Clarify.'}</p></div><span className="chev">›</span></button>)}</div>}
  </div>
}

function MaterialDetail({ material, onDeleted, setError, setBusy, busy }: Common & { material: Material; onDeleted: () => void }) {
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [question, setQuestion] = useState('')
  const actions = useMemo(() => [['✨','summary','Кратко'],['📌','main','Главное'],['✅','tasks','Что делать'],['⚠️','risks','Риски'],['💰','money','Деньги'],['📅','dates','Сроки'],['🧠','plain','Объяснить'],['🎯','wants','Что хотят']], [])

  const run = async (action: string) => {
    setBusy(true); setAnswer(null)
    try { setAnswer(await api<Answer>(`/api/materials/${material.id}/action`, { method: 'POST', body: JSON.stringify({ action }) })); successHaptic() }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось выполнить действие') }
    finally { setBusy(false) }
  }

  const ask = async (e: FormEvent) => {
    e.preventDefault(); if (!question.trim()) return
    setBusy(true); setAnswer(null)
    try { setAnswer(await api<Answer>(`/api/materials/${material.id}/ask`, { method: 'POST', body: JSON.stringify({ question }) })); successHaptic() }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось ответить') }
    finally { setBusy(false) }
  }

  const remove = async () => {
    if (!window.confirm('Удалить этот материал?')) return
    try { await api<{ ok: boolean }>(`/api/materials/${material.id}`, { method: 'DELETE' }); onDeleted() }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось удалить') }
  }

  return <div className="stack material-detail">
    <div className="detail-title"><div className="big-icon">{typeIcon(material.type)}</div><div><span>{prettyType(material.type)} · {formatDate(material.created_at)}</span><h1>{material.title}</h1></div></div>
    <div className="summary-card premium-card"><span className="eyebrow">CLARIFY SUMMARY</span><h3>Кратко</h3><p>{material.summary || 'Материал сохранён. Выбери действие ниже или задай вопрос.'}</p></div>
    <div className="action-grid">{actions.map(([icon,id,label]) => <button key={id} onClick={() => void run(id)}><span>{icon}</span><b>{label}</b></button>)}</div>
    <form className="ask-box premium-card" onSubmit={ask}><div><span className="eyebrow">ASK CLARIFY</span><textarea rows={3} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Спроси что угодно по этому материалу…" /></div><button className="primary" disabled={busy || !question.trim()}>{busy ? 'Думаю…' : 'Спросить ✦'}</button></form>
    {busy && <Loading text="Clarify разбирается…" />}
    {answer && <div className="answer-card"><span className="eyebrow">CLARIFY</span><div className="answer-text">{answer.answer}</div><Sources items={answer.sources} /><div className="answer-tools"><button onClick={() => setQuestion('Сделай ответ короче')}>⚡ Короче</button><button onClick={() => setQuestion('Объясни ещё проще')}>🧠 Проще</button></div></div>}
    <details className="source"><summary>Исходник</summary><pre>{material.text || 'Исходник не сохранён.'}</pre></details>
    <button className="danger ghost" onClick={() => void remove()}>Удалить материал</button>
  </div>
}

function Projects({ items, setItems, open, setError }: Common & { items: Project[]; setItems: (v: Project[]) => void; open: (id: number) => void }) {
  const [name, setName] = useState('')
  const load = useCallback(async () => { try { const data = await api<{items: Project[]}>('/api/projects'); setItems(data.items) } catch(e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить проекты') } }, [setItems, setError])
  useEffect(() => { void load() }, [load])
  const create = async (e: FormEvent) => { e.preventDefault(); if (!name.trim()) return; try { await api<{id:number;name:string}>('/api/projects',{method:'POST',body:JSON.stringify({name})}); setName(''); successHaptic(); await load() } catch(err){ setError(err instanceof Error ? err.message : 'Не удалось создать проект') } }
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">WORKSPACES</span><h1>Проекты</h1><p>Собирай материалы по одной теме.</p></div></div>
    <form className="inline-create premium-card" onSubmit={create}><input value={name} onChange={e=>setName(e.target.value)} placeholder="Например: Закупка №27"/><button>＋</button></form>
    {!items.length ? <Empty title="Проектов пока нет" text="Создай рабочее пространство и собери в нём связанные материалы." /> : <div className="project-grid">{items.map(p=><button className="project-card" key={p.id} onClick={()=>open(p.id)}><div className="folder">▱</div><div><b>{p.name}</b><span>{p.count} материалов</span></div><i>→</i></button>)}</div>}
  </div>
}

function ProjectDetail({ project, setError, setBusy, busy }: Common & { project: Project }) {
  const [question,setQuestion]=useState('')
  const [answer,setAnswer]=useState<Answer|null>(null)
  const ask=async(e:FormEvent)=>{e.preventDefault();if(!question.trim())return;setBusy(true);try{setAnswer(await api<Answer>(`/api/projects/${project.id}/ask`,{method:'POST',body:JSON.stringify({question})}))}catch(err){setError(err instanceof Error?err.message:'Ошибка')}finally{setBusy(false)}}
  return <div className="stack"><div className="detail-title"><div className="big-icon">📁</div><div><span>PROJECT</span><h1>{project.name}</h1></div></div>
    <form className="ask-box premium-card" onSubmit={ask}><textarea rows={3} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Что мы в итоге согласовали по цене?"/><button className="primary" disabled={busy}>{busy?'Собираю…':'Спросить ✦'}</button></form>
    {answer&&<div className="answer-card"><span className="eyebrow">PROJECT ANSWER</span><div className="answer-text">{answer.answer}</div><Sources items={answer.sources}/></div>}
    <h2 className="section-title">Материалы</h2><div className="material-list">{(project.materials||[]).map(m=><div className="material-card static" key={m.id}><div className="material-icon">{typeIcon(m.type)}</div><div className="material-body"><b>{m.title}</b><p>{m.summary}</p></div></div>)}</div>
  </div>
}

function Compare({ setError, setBusy, busy }: Common) {
  const [items,setItems]=useState<Material[]>([]),[a,setA]=useState(''),[b,setB]=useState(''),[answer,setAnswer]=useState('')
  useEffect(()=>{void api<{items:Material[]}>('/api/materials?limit=50').then(d=>setItems(d.items)).catch(e=>setError(e instanceof Error?e.message:'Ошибка'))},[setError])
  const run=async()=>{if(!a||!b||a===b){setError('Выбери два разных материала');return}setBusy(true);setAnswer('');try{const r=await api<{answer:string}>('/api/compare',{method:'POST',body:JSON.stringify({first_id:Number(a),second_id:Number(b)})});setAnswer(r.answer);successHaptic()}catch(e){setError(e instanceof Error?e.message:'Ошибка сравнения')}finally{setBusy(false)}}
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">COMPARE</span><h1>Сравнить</h1><p>Покажи Clarify два материала — он найдёт отличия.</p></div></div><div className="compare-box premium-card"><label>Материал A<select value={a} onChange={e=>setA(e.target.value)}><option value="">Выбрать…</option>{items.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><div className="vs">VS</div><label>Материал B<select value={b} onChange={e=>setB(e.target.value)}><option value="">Выбрать…</option>{items.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><button className="primary wide" onClick={()=>void run()} disabled={busy}>{busy?'Сравниваю…':'🔀 Сравнить материалы'}</button></div>{answer&&<div className="answer-card"><span className="eyebrow">RESULT</span><div className="answer-text">{answer}</div></div>}</div>
}

function Reminders({ setError }: Common) {
  const [items,setItems]=useState<Reminder[]>([]),[text,setText]=useState(''),[when,setWhen]=useState('')
  const load=useCallback(async()=>{try{const d=await api<{items:Reminder[]}>('/api/reminders');setItems(d.items)}catch(e){setError(e instanceof Error?e.message:'Ошибка')}} ,[setError])
  useEffect(()=>{void load()},[load])
  const create=async(e:FormEvent)=>{e.preventDefault();if(!text.trim()||!when)return;try{await api<{id:number}>('/api/reminders',{method:'POST',body:JSON.stringify({text,remind_at:new Date(when).toISOString()})});setText('');setWhen('');successHaptic();await load()}catch(err){setError(err instanceof Error?err.message:'Ошибка')}}
  const remove=async(id:number)=>{try{await api<{ok:boolean}>(`/api/reminders/${id}`,{method:'DELETE'});await load()}catch(e){setError(e instanceof Error?e.message:'Ошибка')}}
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">REMINDERS</span><h1>Напоминания</h1><p>Важное не потеряется после разбора.</p></div></div><form className="reminder-form premium-card" onSubmit={create}><input value={text} onChange={e=>setText(e.target.value)} placeholder="Оплатить поставщику"/><input type="datetime-local" value={when} onChange={e=>setWhen(e.target.value)}/><button className="primary">Создать</button></form>{!items.length?<Empty title="Напоминаний нет" text="Создай первое напоминание."/>:<div className="reminder-list">{items.map(r=><div className={`reminder ${r.status}`} key={r.id}><span>⏰</span><div><b>{r.text}</b><small>{formatDate(r.remind_at)} · {r.status}</small></div><button onClick={()=>void remove(r.id)}>×</button></div>)}</div>}</div>
}

function Compose({ setError, setBusy, busy }: Common) {
  const [brief,setBrief]=useState(''),[answer,setAnswer]=useState('')
  const run=async(e:FormEvent)=>{e.preventDefault();if(!brief.trim())return;setBusy(true);try{const r=await api<{answer:string}>('/api/compose',{method:'POST',body:JSON.stringify({brief})});setAnswer(r.answer);successHaptic()}catch(err){setError(err instanceof Error?err.message:'Ошибка')}finally{setBusy(false)}}
  const rewrite=async(mode:string)=>{if(!answer)return;setBusy(true);try{const r=await api<{answer:string}>('/api/rewrite',{method:'POST',body:JSON.stringify({text:answer,mode})});setAnswer(r.answer)}catch(e){setError(e instanceof Error?e.message:'Ошибка')}finally{setBusy(false)}}
  return <div className="stack"><div className="ai-page-head"><div className="ai-large">✦</div><span className="eyebrow">WRITE WITH CLARIFY</span><h1>Что написать за тебя?</h1><p>Опиши смысл как получится. Clarify превратит его в готовый текст.</p></div><form className="compose premium-card" onSubmit={run}><textarea rows={7} value={brief} onChange={e=>setBrief(e.target.value)} placeholder="Поставщику: товар нужен до пятницы, спроси, успеет ли он…"/><button className="primary wide" disabled={busy||!brief.trim()}>{busy?'Пишу…':'✦ Написать'}</button></form>{busy&&<Loading text="Подбираю формулировку…"/>}{answer&&<><div className="answer-card selectable"><span className="eyebrow">READY TO SEND</span><div className="answer-text">{answer}</div></div><div className="chips rewrite">{[['мягче и теплее','🙂 Мягче'],['официальнее','👔 Официальнее'],['максимально короче','⚡ Короче'],['с лёгким уместным юмором','😄 С юмором'],['убедительнее','🎯 Убедительнее'],['другой вариант','↻ Другой']].map(([mode,label])=><button key={mode} onClick={()=>void rewrite(mode)}>{label}</button>)}</div></>}</div>
}

function Pro({ me, setError, refreshMe }: Common & { refreshMe: () => Promise<void> }) {
  const [loading,setLoading]=useState(false)
  const buy=async()=>{setLoading(true);try{const r=await api<{invoice_url:string}>('/api/pro/invoice',{method:'POST'});openInvoice(r.invoice_url,()=>void refreshMe())}catch(e){setError(e instanceof Error?e.message:'Не удалось открыть оплату')}finally{setLoading(false)}}
  if(me.owner)return <div className="owner-hero premium-card"><div className="crown">👑</div><span className="eyebrow">CLARIFY OWNER</span><h1>Unlimited</h1><p>Для владельца продукта клиентские лимиты отключены.</p></div>
  return <div className="stack"><div className="pro-hero premium-card"><span className="eyebrow">CLARIFY PRO</span><h1>Больше Clarify.<br/>Меньше ограничений.</h1><p>Для ежедневной работы с документами, голосовыми и AI Memory.</p><strong>{me.pro_price} ⭐ <small>/ 30 дней</small></strong><button className="primary wide" disabled={loading||me.plan==='PRO'} onClick={()=>void buy()}>{me.plan==='PRO'?'✦ PRO уже активен':loading?'Открываю Telegram Stars…':'Подключить PRO'}</button></div><div className="benefits">{['🎤 Длинные голосовые','📄 Большие документы','🧠 Больше AI-запросов','📁 Проекты','🔀 Сравнение','✦ Smart AI','⏰ Напоминания'].map(x=><div key={x}>{x}<span>✓</span></div>)}</div></div>
}

function Profile({ me, setError, refreshMe, setPage }: Common & { refreshMe: () => Promise<void> }) {
  const [timezone,setTimezone]=useState(me.timezone),[style,setStyle]=useState(me.style||''),[mode,setMode]=useState(me.ai_mode||'fast'),[saving,setSaving]=useState(false)
  const [stats,setStats]=useState<Stats|null>(null)
  useEffect(()=>{void api<Stats>('/api/profile/stats').then(setStats).catch(()=>undefined)},[])
  const save=async()=>{setSaving(true);try{await api<{ok:boolean}>('/api/settings',{method:'PATCH',body:JSON.stringify({timezone,style,ai_mode:mode})});successHaptic();await refreshMe()}catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить')}finally{setSaving(false)}}
  const erase=async()=>{if(!window.confirm('Удалить материалы, проекты, стиль, AI-историю и напоминания?'))return;try{await api<{ok:boolean}>('/api/me/data',{method:'DELETE'});successHaptic();await refreshMe()}catch(e){setError(e instanceof Error?e.message:'Ошибка')}}
  const limit=me.usage.limit
  const percent=limit?Math.min(100,Math.round(me.usage.used/Math.max(1,limit)*100)):8
  return <div className="stack profile-page"><div className="profile-card premium-card"><div className="avatar">{(me.first_name||'C')[0].toUpperCase()}</div><div><span>{me.username?`@${me.username}`:'Telegram user'}</span><h1>{me.first_name||'Clarify User'}</h1><b className={me.owner?'owner-text':''}>{me.owner?'👑 OWNER · Unlimited':me.plan}</b></div></div>
    <div className="stats-grid"><div><span>Материалы</span><b>{stats?.materials ?? '—'}</b></div><div><span>Проекты</span><b>{stats?.projects ?? '—'}</b></div><div><span>AI сегодня</span><b>{stats?.ai_today ?? me.usage.used}</b></div></div>
    <div className="usage-card premium-card"><div><span className="eyebrow">TODAY</span><b>AI использование</b><small>{me.owner?'Без лимита':`${me.usage.used} из ${limit ?? '∞'}`}</small></div><div className="usage-track"><i style={{width:`${percent}%`}}/></div>{!me.owner&&me.plan==='FREE'&&<button onClick={()=>setPage('pro')}>Увеличить лимиты →</button>}</div>
    <div className="settings-card premium-card"><span className="eyebrow">PREFERENCES</span><label>Часовой пояс<input value={timezone} onChange={e=>setTimezone(e.target.value)}/></label><label>Стиль ответов<textarea rows={3} value={style} onChange={e=>setStyle(e.target.value)} placeholder="Коротко, разговорно, без канцелярита"/></label><label>AI режим<div className="segmented"><button className={mode==='fast'?'active':''} onClick={()=>setMode('fast')} type="button">⚡ Быстро</button><button className={mode==='smart'?'active':''} onClick={()=>setMode('smart')} type="button">🧠 Умно</button></div></label><button className="primary wide" disabled={saving} onClick={()=>void save()}>{saving?'Сохраняю…':'Сохранить настройки'}</button></div>
    <div className="data-card"><b>Приватность</b><p>Ты можешь удалить материалы, проекты, настройки и AI-историю в любой момент.</p><button className="danger ghost" onClick={()=>void erase()}>Удалить мои данные</button></div><div className="version">Clarify {me.version}</div></div>
}

function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0)
  const slides = [
    { icon: '✦', eyebrow: 'WELCOME', title: 'Добро пожаловать в Clarify', text: 'Твой AI Workspace для понимания информации без лишней рутины.', chips: ['AI Inbox', 'Memory', 'Projects'] },
    { icon: '⌁', eyebrow: 'SEND ANYTHING', title: 'Добавляй что угодно', text: 'Голосовые, документы, скриншоты, ссылки и обычный текст — прямо внутри Mini App.', chips: ['🎤 Voice', '📄 Docs', '🖼 Screens', '🔗 Links'] },
    { icon: '🧠', eyebrow: 'GET CLARITY', title: 'Получай ясный результат', text: 'Кратко, главное, действия, сроки, суммы, риски и ответы на твои вопросы.', chips: ['✨ Кратко', '📌 Главное', '✅ Действия'] },
  ]
  const slide = slides[step]
  return <div className="onboarding"><div className="onboard-card"><button className="skip" onClick={onDone}>Пропустить</button><div className="onboard-orb">{slide.icon}</div><span className="eyebrow">{slide.eyebrow}</span><h1>{slide.title}</h1><p>{slide.text}</p><div className="onboard-chips">{slide.chips.map(x=><span key={x}>{x}</span>)}</div><div className="dots">{slides.map((_,i)=><i key={i} className={i===step?'active':''}/>)}</div><button className="primary wide" onClick={()=>step<slides.length-1?setStep(step+1):onDone()}>{step<slides.length-1?'Дальше →':'Начать ✦'}</button></div></div>
}

export default App
