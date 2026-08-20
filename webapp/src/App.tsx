import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { api, closeToChat, haptic, hasTelegramAuth, Material, Me, openInvoice, successHaptic } from './api'

type Page = 'home' | 'materials' | 'projects' | 'profile' | 'material' | 'project' | 'compare' | 'reminders' | 'compose' | 'pro'
type Project = { id: number; name: string; count: number; created_at?: string | null; materials?: Material[] }
type Reminder = { id: number; text: string; remind_at: string; status: string }
type Source = { title: string; page: number }

type Answer = { answer: string; sources?: Source[] }

const typeIcon = (type: string) => {
  if (['voice', 'audio'].includes(type)) return '🎤'
  if (['image', 'screenshot'].includes(type)) return '📸'
  if (type === 'link') return '🔗'
  if (['pdf', 'docx', 'document'].includes(type)) return '📄'
  if (['xlsx', 'csv', 'spreadsheet'].includes(type)) return '📊'
  if (type === 'forwarded') return '💬'
  return '📝'
}

const prettyType = (type: string) => ({
  voice: 'Голосовое', audio: 'Аудио', image: 'Изображение', screenshot: 'Скриншот', link: 'Ссылка',
  pdf: 'PDF', docx: 'DOCX', document: 'Документ', spreadsheet: 'Таблица', xlsx: 'XLSX', csv: 'CSV',
  forwarded: 'Сообщение', draft: 'Черновик', text: 'Текст',
}[type] || type)

const formatDate = (value?: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function Loading({ text = 'Загружаю…' }: { text?: string }) {
  return <div className="loading-card"><div className="orb" /><span>{text}</span></div>
}

function Empty({ title, text, action }: { title: string; text: string; action?: () => void }) {
  return <div className="empty"><div className="empty-icon">✦</div><h3>{title}</h3><p>{text}</p>{action && <button className="primary" onClick={action}>📎 Перейти в чат</button>}</div>
}

function Sources({ items = [] }: { items?: Source[] }) {
  if (!items.length) return null
  return <div className="sources"><span>Источник</span>{items.map((s, i) => <div key={`${s.title}-${s.page}-${i}`}>📄 {s.title} · стр. {s.page}</div>)}</div>
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

  useEffect(() => {
    tg?.ready()
    tg?.expand()
    tg?.setHeaderColor?.('#071125')
    tg?.setBackgroundColor?.('#071125')
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
      if (['material', 'project'].includes(page)) setPage(page === 'material' ? 'materials' : 'projects')
      else if (!['home', 'materials', 'projects', 'profile'].includes(page)) setPage('home')
      else setPage('home')
    }
    if (page !== 'home') tg.BackButton.show(); else tg.BackButton.hide()
    tg.BackButton.onClick(handler)
    return () => tg.BackButton?.offClick(handler)
  }, [page, tg])

  const navigate = (next: Page) => { haptic(); setGlobalError(''); setPage(next) }

  if (!hasTelegramAuth()) {
    return <main className="outside"><img src="/assets/clarify-banner.webp" alt="Clarify" /><div className="glass"><h1>Clarify</h1><p>Mini App защищён Telegram-авторизацией.</p><b>Открой его кнопкой «🚀 Открыть Clarify» внутри бота.</b></div></main>
  }

  if (!me && !globalError) return <main className="app-shell"><Loading text="Открываю Clarify…" /></main>
  if (!me) return <main className="outside"><div className="glass"><h2>Не получилось открыть Clarify</h2><p>{globalError}</p><button className="primary" onClick={() => void refreshMe()}>Попробовать снова</button></div></main>

  const common = { me, setPage: navigate, setError: setGlobalError, busy, setBusy }

  return <div className="app-shell">
    <div className="ambient ambient-a" /><div className="ambient ambient-b" />
    <header className="topbar">
      <div className="brand"><div className="brand-mark">✦</div><div><strong>Clarify</strong><span>{me.owner ? 'OWNER · Unlimited' : me.plan}</span></div></div>
      <button className={`plan-pill ${me.owner ? 'owner' : ''}`} onClick={() => navigate(me.owner ? 'profile' : 'pro')}>{me.owner ? '👑 OWNER' : me.plan === 'PRO' ? '👑 PRO' : `${me.usage.used}/${me.usage.limit ?? '∞'}`}</button>
    </header>

    {globalError && <div className="toast error" onClick={() => setGlobalError('')}>{globalError}<span>×</span></div>}

    <section className="page">
      {page === 'home' && <Home {...common} />}
      {page === 'materials' && <Materials {...common} items={materials} setItems={setMaterials} open={async id => {
        setBusy(true)
        try { const item = await api<Material>(`/api/materials/${id}`); setSelectedMaterial(item); setPage('material') } catch (e) { setGlobalError(e instanceof Error ? e.message : 'Ошибка') } finally { setBusy(false) }
      }} />}
      {page === 'material' && selectedMaterial && <MaterialDetail {...common} material={selectedMaterial} onDeleted={() => { setSelectedMaterial(null); setPage('materials') }} />}
      {page === 'projects' && <Projects {...common} items={projects} setItems={setProjects} open={async id => {
        setBusy(true)
        try { const item = await api<Project>(`/api/projects/${id}`); setSelectedProject(item); setPage('project') } catch (e) { setGlobalError(e instanceof Error ? e.message : 'Ошибка') } finally { setBusy(false) }
      }} />}
      {page === 'project' && selectedProject && <ProjectDetail {...common} project={selectedProject} />}
      {page === 'compare' && <Compare {...common} />}
      {page === 'reminders' && <Reminders {...common} />}
      {page === 'compose' && <Compose {...common} />}
      {page === 'pro' && <Pro {...common} refreshMe={refreshMe} />}
      {page === 'profile' && <Profile {...common} refreshMe={refreshMe} />}
    </section>

    <nav className="bottom-nav">
      {([['home', '⌂', 'Главная'], ['materials', '◈', 'Материалы'], ['projects', '▣', 'Проекты'], ['profile', '◎', 'Профиль']] as const).map(([id, icon, label]) =>
        <button key={id} className={page === id || (id === 'materials' && page === 'material') || (id === 'projects' && page === 'project') ? 'active' : ''} onClick={() => navigate(id)}><span>{icon}</span>{label}</button>
      )}
    </nav>
  </div>
}

type Common = { me: Me; setPage: (p: Page) => void; setError: (s: string) => void; busy: boolean; setBusy: (b: boolean) => void }

function Home({ me, setPage }: Common) {
  return <>
    <div className="hero">
      <img src="/assets/clarify-banner.webp" alt="Clarify — Send anything. Get clarity." />
      <div className="hero-copy"><span className="eyebrow">AI INBOX · TELEGRAM</span><h1>Что разберём сегодня?</h1><p>Отправь то, на что не хочется тратить время. Clarify превратит входящий хаос в ясный результат.</p><button className="primary wide" onClick={() => { haptic('medium'); closeToChat() }}>📎 Отправить материал</button></div>
    </div>
    <div className="format-row"><span>🎤 Voice</span><span>📄 Docs</span><span>📸 Screens</span><span>🔗 Links</span></div>
    <h2 className="section-title">Быстрые действия</h2>
    <div className="quick-grid">
      <Quick icon="🧠" title="Материалы" text="История и поиск" onClick={() => setPage('materials')} />
      <Quick icon="📁" title="Проекты" text="Всё по одной теме" onClick={() => setPage('projects')} />
      <Quick icon="🔀" title="Сравнить" text="Два материала" onClick={() => setPage('compare')} />
      <Quick icon="⏰" title="Напоминания" text="Не забыть важное" onClick={() => setPage('reminders')} />
      <Quick icon="✍️" title="Написать" text="Готовый ответ" onClick={() => setPage('compose')} />
      <Quick icon={me.owner ? '👑' : '⚡'} title={me.owner ? 'OWNER' : 'Clarify PRO'} text={me.owner ? 'Unlimited access' : 'Больше возможностей'} onClick={() => setPage(me.owner ? 'profile' : 'pro')} />
    </div>
    <div className="insight-card"><div className="spark">✦</div><div><b>Не думай, что спросить у AI.</b><p>Просто перешли Clarify голосовое, договор, скрин или ссылку — он сам предложит полезные действия.</p></div></div>
  </>
}

function Quick({ icon, title, text, onClick }: { icon: string; title: string; text: string; onClick: () => void }) {
  return <button className="quick" onClick={() => { haptic(); onClick() }}><span className="quick-icon">{icon}</span><b>{title}</b><small>{text}</small></button>
}

function Materials({ items, setItems, open, setError }: Common & { items: Material[]; setItems: (v: Material[]) => void; open: (id: number) => void }) {
  const [q, setQ] = useState('')
  const [type, setType] = useState('all')
  const [period, setPeriod] = useState('all')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        const params = new URLSearchParams({ limit: '30', type, period })
        if (q.trim()) params.set('q', q.trim())
        const data = await api<{ items: Material[] }>(`/api/materials?${params}`)
        setItems(data.items)
      } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить материалы') } finally { setLoading(false) }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [q, type, period, setItems, setError])

  return <div className="stack"><div className="page-head"><div><span className="eyebrow">LIBRARY</span><h1>Мои материалы</h1></div><button className="icon-btn" onClick={closeToChat}>＋</button></div>
    <div className="search"><span>⌕</span><input value={q} onChange={e => setQ(e.target.value)} placeholder="Найти договор, голосовое, сумму…" /></div>
    <div className="chips">{[['all','Все'],['documents','Документы'],['voice','Голосовые'],['images','Фото'],['links','Ссылки'],['text','Текст']].map(([id,label]) => <button key={id} className={type===id?'active':''} onClick={() => setType(id)}>{label}</button>)}</div>
    <div className="chips subtle">{[['all','Все время'],['today','Сегодня'],['week','Неделя']].map(([id,label]) => <button key={id} className={period===id?'active':''} onClick={() => setPeriod(id)}>{label}</button>)}</div>
    {loading ? <Loading text="Ищу материалы…" /> : !items.length ? <Empty title="Здесь пока пусто" text="Перешли Clarify документ, голосовое, фото или ссылку." action={closeToChat} /> : <div className="material-list">{items.map(item => <button className="material-card" key={item.id} onClick={() => open(item.id)}><div className="material-icon">{typeIcon(item.type)}</div><div className="material-body"><div className="material-meta"><span>{prettyType(item.type)}</span><time>{formatDate(item.created_at)}</time></div><b>{item.title}</b><p>{item.summary || 'Материал сохранён. Открой, чтобы спросить Clarify.'}</p></div><span className="chev">›</span></button>)}</div>}
  </div>
}

function MaterialDetail({ material, onDeleted, setError, setBusy, busy }: Common & { material: Material; onDeleted: () => void }) {
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [question, setQuestion] = useState('')
  const actions = useMemo(() => [['✨','summary','Кратко'],['📌','main','Главное'],['✅','tasks','Задачи'],['⚠️','risks','Риски'],['💰','money','Деньги'],['📅','dates','Сроки'],['👶','plain','Просто'],['🎯','wants','Что хотят']], [])

  const run = async (action: string) => {
    setBusy(true); setAnswer(null)
    try { setAnswer(await api<Answer>(`/api/materials/${material.id}/action`, { method: 'POST', body: JSON.stringify({ action }) })); successHaptic() }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось выполнить действие') } finally { setBusy(false) }
  }
  const ask = async (e: FormEvent) => {
    e.preventDefault(); if (!question.trim()) return
    setBusy(true); setAnswer(null)
    try { setAnswer(await api<Answer>(`/api/materials/${material.id}/ask`, { method: 'POST', body: JSON.stringify({ question }) })); successHaptic() }
    catch (err) { setError(err instanceof Error ? err.message : 'Не удалось ответить') } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!window.confirm('Удалить этот материал?')) return
    try { await api(`/api/materials/${material.id}`, { method: 'DELETE' }); onDeleted() } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось удалить') }
  }

  return <div className="stack"><div className="detail-title"><div className="big-icon">{typeIcon(material.type)}</div><div><span>{prettyType(material.type)} · {formatDate(material.created_at)}</span><h1>{material.title}</h1></div></div>
    {material.summary && <div className="summary-card"><span className="eyebrow">КОРОТКО</span><p>{material.summary}</p></div>}
    <div className="action-scroll">{actions.map(([icon,id,label]) => <button key={id} onClick={() => void run(id)}><span>{icon}</span>{label}</button>)}</div>
    <form className="ask-box" onSubmit={ask}><textarea rows={3} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Спросить Clarify по этому материалу…" /><button className="primary" disabled={busy}>{busy ? 'Ищу нужный пункт…' : 'Спросить ✦'}</button></form>
    {busy && <Loading text="Clarify разбирается…" />}
    {answer && <div className="answer-card"><span className="eyebrow">CLARIFY</span><div className="answer-text">{answer.answer}</div><Sources items={answer.sources} /></div>}
    <details className="source"><summary>📄 Исходник</summary><pre>{material.text || 'Исходник не сохранён.'}</pre></details>
    <button className="danger ghost" onClick={() => void remove()}>🗑 Удалить материал</button>
  </div>
}

function Projects({ items, setItems, open, setError }: Common & { items: Project[]; setItems: (v: Project[]) => void; open: (id: number) => void }) {
  const [name, setName] = useState('')
  const load = useCallback(async () => { try { const data = await api<{items: Project[]}>('/api/projects'); setItems(data.items) } catch(e) { setError(e instanceof Error ? e.message : 'Не удалось загрузить проекты') } }, [setItems, setError])
  useEffect(() => { void load() }, [load])
  const create = async (e: FormEvent) => { e.preventDefault(); if (!name.trim()) return; try { await api('/api/projects',{method:'POST',body:JSON.stringify({name})}); setName(''); successHaptic(); await load() } catch(err){ setError(err instanceof Error ? err.message : 'Не удалось создать проект') } }
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">WORKSPACES</span><h1>Проекты</h1></div></div>
    <form className="inline-create" onSubmit={create}><input value={name} onChange={e=>setName(e.target.value)} placeholder="Новый проект, например Закупка №27"/><button>＋</button></form>
    {!items.length ? <Empty title="Проектов пока нет" text="Собирай связанные документы, голосовые и переписки в одну рабочую тему." /> : <div className="project-grid">{items.map(p=><button className="project-card" key={p.id} onClick={()=>open(p.id)}><div className="folder">▱</div><b>{p.name}</b><span>{p.count} материалов</span><i>Открыть →</i></button>)}</div>}
  </div>
}

function ProjectDetail({ project, setError, setBusy, busy }: Common & { project: Project }) {
  const [question,setQuestion]=useState('')
  const [answer,setAnswer]=useState<Answer|null>(null)
  const ask=async(e:FormEvent)=>{e.preventDefault();if(!question.trim())return;setBusy(true);try{setAnswer(await api<Answer>(`/api/projects/${project.id}/ask`,{method:'POST',body:JSON.stringify({question})}))}catch(err){setError(err instanceof Error?err.message:'Ошибка')}finally{setBusy(false)}}
  return <div className="stack"><div className="detail-title"><div className="big-icon">📁</div><div><span>ПРОЕКТ</span><h1>{project.name}</h1></div></div>
    <form className="ask-box" onSubmit={ask}><textarea rows={3} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Что мы в итоге согласовали по цене?"/><button className="primary" disabled={busy}>{busy?'Собираю контекст…':'🧠 Спросить по проекту'}</button></form>
    {answer&&<div className="answer-card"><span className="eyebrow">ПО ПРОЕКТУ</span><div className="answer-text">{answer.answer}</div><Sources items={answer.sources}/></div>}
    <h2 className="section-title">Материалы</h2><div className="material-list">{(project.materials||[]).map(m=><div className="material-card static" key={m.id}><div className="material-icon">{typeIcon(m.type)}</div><div className="material-body"><b>{m.title}</b><p>{m.summary}</p></div></div>)}</div>
  </div>
}

function Compare({ setError, setBusy, busy }: Common) {
  const [items,setItems]=useState<Material[]>([]),[a,setA]=useState(''),[b,setB]=useState(''),[answer,setAnswer]=useState('')
  useEffect(()=>{void api<{items:Material[]}>('/api/materials?limit=50').then(d=>setItems(d.items)).catch(e=>setError(e instanceof Error?e.message:'Ошибка'))},[setError])
  const run=async()=>{if(!a||!b||a===b){setError('Выбери два разных материала');return}setBusy(true);setAnswer('');try{const r=await api<{answer:string}>('/api/compare',{method:'POST',body:JSON.stringify({first_id:Number(a),second_id:Number(b)})});setAnswer(r.answer);successHaptic()}catch(e){setError(e instanceof Error?e.message:'Ошибка сравнения')}finally{setBusy(false)}}
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">COMPARE</span><h1>Сравнить</h1></div></div><div className="compare-box"><label>Материал A<select value={a} onChange={e=>setA(e.target.value)}><option value="">Выбрать…</option>{items.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><div className="vs">VS</div><label>Материал B<select value={b} onChange={e=>setB(e.target.value)}><option value="">Выбрать…</option>{items.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><button className="primary wide" onClick={()=>void run()} disabled={busy}>{busy?'Сравниваю условия…':'🔀 Сравнить'}</button></div>{answer&&<div className="answer-card"><span className="eyebrow">РЕЗУЛЬТАТ</span><div className="answer-text">{answer}</div></div>}</div>
}

function Reminders({ setError }: Common) {
  const [items,setItems]=useState<Reminder[]>([]),[text,setText]=useState(''),[when,setWhen]=useState('')
  const load=useCallback(async()=>{try{const d=await api<{items:Reminder[]}>('/api/reminders');setItems(d.items)}catch(e){setError(e instanceof Error?e.message:'Ошибка')}} ,[setError])
  useEffect(()=>{void load()},[load])
  const create=async(e:FormEvent)=>{e.preventDefault();if(!text.trim()||!when)return;try{await api('/api/reminders',{method:'POST',body:JSON.stringify({text,remind_at:new Date(when).toISOString()})});setText('');setWhen('');successHaptic();await load()}catch(err){setError(err instanceof Error?err.message:'Ошибка')}}
  const remove=async(id:number)=>{try{await api(`/api/reminders/${id}`,{method:'DELETE'});await load()}catch(e){setError(e instanceof Error?e.message:'Ошибка')}}
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">REMINDERS</span><h1>Напоминания</h1></div></div><form className="reminder-form" onSubmit={create}><input value={text} onChange={e=>setText(e.target.value)} placeholder="Оплатить поставщику"/><input type="datetime-local" value={when} onChange={e=>setWhen(e.target.value)}/><button className="primary">⏰ Создать</button></form>{!items.length?<Empty title="Напоминаний нет" text="Создай напоминание из Mini App или прямо после разбора материала."/>:<div className="reminder-list">{items.map(r=><div className={`reminder ${r.status}`} key={r.id}><span>⏰</span><div><b>{r.text}</b><small>{formatDate(r.remind_at)} · {r.status}</small></div><button onClick={()=>void remove(r.id)}>×</button></div>)}</div>}</div>
}

function Compose({ setError, setBusy, busy }: Common) {
  const [brief,setBrief]=useState(''),[answer,setAnswer]=useState('')
  const run=async(e:FormEvent)=>{e.preventDefault();if(!brief.trim())return;setBusy(true);try{const r=await api<{answer:string}>('/api/compose',{method:'POST',body:JSON.stringify({brief})});setAnswer(r.answer);successHaptic()}catch(err){setError(err instanceof Error?err.message:'Ошибка')}finally{setBusy(false)}}
  const rewrite=async(mode:string)=>{if(!answer)return;setBusy(true);try{const r=await api<{answer:string}>('/api/rewrite',{method:'POST',body:JSON.stringify({text:answer,mode})});setAnswer(r.answer)}catch(e){setError(e instanceof Error?e.message:'Ошибка')}finally{setBusy(false)}}
  return <div className="stack"><div className="page-head"><div><span className="eyebrow">WRITE FOR ME</span><h1>Написать за меня</h1></div></div><form className="compose" onSubmit={run}><textarea rows={6} value={brief} onChange={e=>setBrief(e.target.value)} placeholder="Поставщику: товар нужен до пятницы, спроси, успеет ли он."/><button className="primary wide" disabled={busy}>{busy?'Пишу в твоём стиле…':'✨ Написать'}</button></form>{answer&&<><div className="answer-card selectable"><div className="answer-text">{answer}</div></div><div className="chips rewrite">{[['мягче и теплее','🙂 Мягче'],['официальнее','👔 Официальнее'],['максимально короче','⚡ Короче'],['с лёгким уместным юмором','😄 С юмором'],['убедительнее','🎯 Убедительнее'],['другой вариант','🔄 Другой']].map(([mode,label])=><button key={mode} onClick={()=>void rewrite(mode)}>{label}</button>)}</div></>}</div>
}

function Pro({ me, setError, refreshMe }: Common & { refreshMe: () => Promise<void> }) {
  const [loading,setLoading]=useState(false)
  const buy=async()=>{setLoading(true);try{const r=await api<{invoice_url:string}>('/api/pro/invoice',{method:'POST'});openInvoice(r.invoice_url,()=>void refreshMe())}catch(e){setError(e instanceof Error?e.message:'Не удалось открыть оплату')}finally{setLoading(false)}}
  if(me.owner)return <div className="owner-hero"><div>👑</div><span>CLARIFY OWNER</span><h1>Unlimited</h1><p>Для владельца продукта клиентские лимиты отключены. PRO покупать не нужно.</p></div>
  return <div className="stack"><div className="pro-hero"><span className="eyebrow">CLARIFY PRO</span><h1>Работай без лишних ограничений.</h1><p>Для тех, кто реально использует Clarify каждый день.</p><strong>{me.pro_price} ⭐ <small>/ 30 дней</small></strong><button className="primary wide" disabled={loading||me.plan==='PRO'} onClick={()=>void buy()}>{me.plan==='PRO'?'👑 PRO уже активен':loading?'Открываю Telegram Stars…':'👑 Подключить PRO'}</button></div><div className="benefits">{['🎤 Длинные голосовые','📄 Большие документы','🧠 Больше AI-запросов','📁 Проекты','🔀 Сравнение','⚡ Smart AI','⏰ Напоминания'].map(x=><div key={x}>{x}<span>✓</span></div>)}</div></div>
}

function Profile({ me, setError, refreshMe }: Common & { refreshMe: () => Promise<void> }) {
  const [timezone,setTimezone]=useState(me.timezone),[style,setStyle]=useState(me.style||''),[mode,setMode]=useState(me.ai_mode||'fast'),[saving,setSaving]=useState(false)
  const save=async()=>{setSaving(true);try{await api('/api/settings',{method:'PATCH',body:JSON.stringify({timezone,style,ai_mode:mode})});successHaptic();await refreshMe()}catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить')}finally{setSaving(false)}}
  const erase=async()=>{if(!window.confirm('Удалить материалы, проекты, стиль, AI-историю и напоминания?'))return;try{await api('/api/me/data',{method:'DELETE'});successHaptic();await refreshMe()}catch(e){setError(e instanceof Error?e.message:'Ошибка')}}
  return <div className="stack"><div className="profile-card"><div className="avatar">{(me.first_name||'C')[0].toUpperCase()}</div><div><span>{me.username?`@${me.username}`:'Telegram'}</span><h1>{me.first_name||'Clarify User'}</h1><b className={me.owner?'owner-text':''}>{me.owner?'👑 OWNER · Unlimited':me.plan}</b></div></div><div className="settings-card"><label>Часовой пояс<input value={timezone} onChange={e=>setTimezone(e.target.value)}/></label><label>Стиль ответов<textarea rows={3} value={style} onChange={e=>setStyle(e.target.value)} placeholder="Коротко, разговорно, без канцелярита"/></label><label>AI режим<div className="segmented"><button className={mode==='fast'?'active':''} onClick={()=>setMode('fast')} type="button">⚡ Быстро</button><button className={mode==='smart'?'active':''} onClick={()=>setMode('smart')} type="button">🧠 Умно</button></div></label><button className="primary wide" disabled={saving} onClick={()=>void save()}>{saving?'Сохраняю…':'Сохранить настройки'}</button></div><div className="data-card"><b>Приватность</b><p>Материалы хранятся для истории и контекстных вопросов. Финансовые записи Stars сохраняются отдельно для учёта.</p><button className="danger ghost" onClick={()=>void erase()}>Удалить мои данные</button></div><div className="version">Clarify {me.version}</div></div>
}

export default App
