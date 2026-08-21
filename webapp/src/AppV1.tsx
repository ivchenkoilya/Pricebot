import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft, Bell, Brain, Check, ChevronRight, CircleAlert, Clock3, Copy, Crown, FileText,
  Folder, GitCompare, House, Image as ImageIcon, Link2, LoaderCircle, Mic, PenLine, Plus,
  Search, Settings2, Sparkles, Trash2, Type, UserRound, WandSparkles, Zap,
} from 'lucide-react'
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

function MaterialGlyph({ type, size = 20 }: { type: string; size?: number }) {
  if (['voice', 'audio'].includes(type)) return <Mic size={size} />
  if (['image', 'screenshot'].includes(type)) return <ImageIcon size={size} />
  if (['link', 'video', 'video_link'].includes(type)) return <Link2 size={size} />
  if (type === 'text' || type === 'forwarded' || type === 'draft') return <Type size={size} />
  return <FileText size={size} />
}

function Loading({ text = 'Загружаю…' }: { text?: string }) {
  return <div className="v1-loading"><span className="v1-spinner"><LoaderCircle size={20} /></span><div><b>{text}</b><small>Clarify уже работает</small></div></div>
}

function SkeletonList() {
  return <div className="v1-skeleton-list">{[0, 1, 2].map(x => <div className="v1-skeleton-card" key={x}><i /><div><b /><span /><span /></div></div>)}</div>
}

function Empty({ icon = <Sparkles size={25} />, title, text, action }: { icon?: React.ReactNode; title: string; text: string; action?: () => void }) {
  return <div className="v1-empty"><span>{icon}</span><h3>{title}</h3><p>{text}</p>{action && <button className="v1-primary small" onClick={action}><Plus size={17} /> Добавить материал</button>}</div>
}

function Sources({ items = [], onOpen }: { items?: Source[]; onOpen?: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false)
  if (!items.length) return null
  const shown = expanded ? items : items.slice(0, 3)
  return <div className="v1-sources"><div className="v1-sources-head"><span>Источники</span><small>{items.length}</small></div>{shown.map((s, i) => <button disabled={!s.id || !onOpen} onClick={() => s.id && onOpen?.(s.id)} key={`${s.id || 0}-${s.title}-${s.page || 0}-${i}`}><span className="source-icon"><MaterialGlyph type={s.type || 'document'} size={15} /></span><div><b>{s.title}</b><small>{s.page ? `Страница ${s.page}` : 'Материал Clarify'}</small></div>{s.id && onOpen ? <ChevronRight size={16} /> : null}</button>)}{items.length > 3 && <button className="v1-source-more" onClick={() => setExpanded(v => !v)}>{expanded ? 'Скрыть' : `Показать ещё ${items.length - 3}`}</button>}</div>
}

function AppV1() {
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
  const [showOnboarding, setShowOnboarding] = useState(() => window.localStorage.getItem('clarify_onboarding_v3') !== 'done')

  useEffect(() => {
    tg?.ready(); tg?.expand(); tg?.setHeaderColor?.('#061126'); tg?.setBackgroundColor?.('#061126')
  }, [tg])

  const refreshMe = useCallback(async () => {
    try { setMe(await api<Me>('/api/me')); setGlobalError('') }
    catch (err) { setGlobalError(err instanceof Error ? err.message : 'Не удалось открыть Clarify') }
  }, [])

  useEffect(() => { if (hasTelegramAuth()) void refreshMe() }, [refreshMe])

  const navigate = useCallback((next: Page) => {
    haptic(); setGlobalError(''); setIntakeOpen(false); setIntakeKind(null); setPage(next)
  }, [])

  const openIntake = useCallback((kind: IntakeKind | null = null) => {
    haptic('medium'); setIntakeKind(kind); setIntakeOpen(true)
  }, [])

  const openMaterial = useCallback(async (id: number) => {
    setBusy(true)
    try { setSelectedMaterial(await api<Material>(`/api/materials/${id}`)); setPage('material') }
    catch (e) { setGlobalError(e instanceof Error ? e.message : 'Не удалось открыть материал') }
    finally { setBusy(false) }
  }, [])

  useEffect(() => {
    if (!tg?.BackButton) return
    const handler = () => {
      if (intakeOpen) { setIntakeOpen(false); setIntakeKind(null); return }
      if (page === 'material') setPage('materials')
      else if (page === 'project') setPage('projects')
      else if (page !== 'home') setPage('home')
      else tg.close?.()
    }
    if (page !== 'home' || intakeOpen) tg.BackButton.show(); else tg.BackButton.hide()
    tg.BackButton.onClick(handler)
    return () => tg.BackButton?.offClick(handler)
  }, [page, intakeOpen, tg])

  const intakeDone = (item: Material) => {
    successHaptic(); setIntakeOpen(false); setIntakeKind(null); setSelectedMaterial(item)
    setMaterials(current => [item, ...current.filter(x => x.id !== item.id)]); setPage('material')
  }

  if (!hasTelegramAuth()) return <main className="v1-outside"><img src="/assets/clarify-banner.webp?v=100" alt="Clarify"/><div><span className="v1-eyebrow">TELEGRAM MINI APP</span><h1>Clarify</h1><p>Открой Mini App кнопкой внутри бота.</p></div></main>
  if (!me && !globalError) return <main className="v1-shell v1-boot"><Loading text="Открываю Clarify 1.0…" /></main>
  if (!me) return <main className="v1-outside"><div><CircleAlert size={30}/><h2>Не получилось открыть Clarify</h2><p>{globalError}</p><button className="v1-primary" onClick={() => void refreshMe()}>Попробовать снова</button></div></main>

  const common = { me, setPage: navigate, setError: setGlobalError, busy, setBusy }

  return <div className="v1-shell">
    <div className="v1-ambient one"/><div className="v1-ambient two"/>
    <header className="v1-topbar">
      <button className="v1-brand" onClick={() => navigate('home')}><span><Sparkles size={22}/></span><div><b>Clarify</b><small>AI Workspace</small></div></button>
      <button className={`v1-plan ${me.owner ? 'owner' : ''}`} onClick={() => navigate(me.owner ? 'profile' : 'pro')}>{me.owner ? <><Crown size={15}/> OWNER</> : me.plan === 'PRO' ? <><Sparkles size={15}/> PRO</> : 'FREE'}</button>
    </header>

    {globalError && <div className="v1-toast"><CircleAlert size={18}/><div><b>Не получилось</b><span>{globalError}</span></div><button onClick={() => setGlobalError('')}>×</button></div>}

    <main className="v1-page">
      {page === 'home' && <Home {...common} onAdd={openIntake} openMaterial={openMaterial}/>} 
      {page === 'materials' && <Materials {...common} items={materials} setItems={setMaterials} open={openMaterial} onAdd={openIntake}/>} 
      {page === 'material' && selectedMaterial && <MaterialDetail {...common} material={selectedMaterial} openMaterial={openMaterial} onDeleted={() => { setSelectedMaterial(null); setPage('materials') }}/>} 
      {page === 'projects' && <Projects {...common} items={projects} setItems={setProjects} open={async id => { setBusy(true); try { setSelectedProject(await api<Project>(`/api/projects/${id}`)); setPage('project') } catch(e) { setGlobalError(e instanceof Error ? e.message : 'Не удалось открыть проект') } finally { setBusy(false) } }}/>} 
      {page === 'project' && selectedProject && <ProjectDetail {...common} project={selectedProject} openMaterial={openMaterial}/>} 
      {page === 'compare' && <Compare {...common}/>} 
      {page === 'reminders' && <Reminders {...common}/>} 
      {page === 'compose' && <Compose {...common}/>} 
      {page === 'pro' && <Pro {...common} refreshMe={refreshMe}/>} 
      {page === 'profile' && <Profile {...common} refreshMe={refreshMe}/>} 
    </main>

    <nav className="v1-dock" aria-label="Основная навигация">
      <NavButton active={page === 'home'} label="Главная" icon={<House/>} onClick={() => navigate('home')}/>
      <NavButton active={page === 'materials' || page === 'material'} label="Memory" icon={<Brain/>} onClick={() => navigate('materials')}/>
      <button className="v1-nav-plus" onClick={() => openIntake()} aria-label="Добавить материал"><Plus/></button>
      <NavButton active={page === 'compose'} label="AI" icon={<Sparkles/>} onClick={() => navigate('compose')}/>
      <NavButton active={page === 'profile' || page === 'pro'} label="Профиль" icon={<UserRound/>} onClick={() => navigate('profile')}/>
    </nav>

    <IntakeSheet open={intakeOpen} kind={intakeKind} onKind={setIntakeKind} onClose={() => { if (!busy) { setIntakeOpen(false); setIntakeKind(null) } }} onDone={intakeDone} setError={setGlobalError}/>
    {showOnboarding && <Onboarding onDone={() => { window.localStorage.setItem('clarify_onboarding_v3', 'done'); setShowOnboarding(false) }}/>} 
  </div>
}

function NavButton({ active, label, icon, onClick }: { active: boolean; label: string; icon: React.ReactNode; onClick: () => void }) {
  return <button className={active ? 'active' : ''} onClick={onClick}><span>{icon}</span><small>{label}</small><i/></button>
}

function Home({ me, setPage, onAdd, openMaterial }: Common & { onAdd: (kind?: IntakeKind | null) => void; openMaterial: (id: number) => Promise<void> }) {
  const [recent, setRecent] = useState<Material[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  useEffect(() => {
    void Promise.all([api<{items: Material[]}>('/api/materials?limit=3'), api<Stats>('/api/profile/stats')]).then(([m, s]) => { setRecent(m.items); setStats(s) }).catch(() => undefined)
  }, [])
  const formats = [
    ['audio', <Mic/>, 'Голос'], ['document', <FileText/>, 'Документ'], ['image', <ImageIcon/>, 'Скрин'], ['link', <Link2/>, 'Ссылка'], ['text', <Type/>, 'Текст'],
  ] as const
  return <div className="v1-stack home">
    <section className="v1-hero">
      <img src="/assets/clarify-banner.webp?v=100" alt="Clarify — Send anything. Get clarity."/>
      <div className="v1-hero-copy"><span className="v1-eyebrow">AI INBOX · TELEGRAM</span><h1>Что разберём сегодня?</h1><p>Отправь материал — Clarify найдёт главное, действия, сроки и риски.</p><button className="v1-primary hero" onClick={() => onAdd()}><Plus size={20}/> Добавить материал</button></div>
    </section>

    <div className="v1-format-grid">{formats.map(([id, icon, label]) => <button key={id} onClick={() => onAdd(id)}><span>{icon}</span><small>{label}</small></button>)}</div>

    {stats && stats.materials > 0 && <section className="v1-today"><div><span className="v1-eyebrow">TODAY IN CLARIFY</span><h2>Сегодня в Clarify</h2></div><div className="v1-today-stats"><span><b>{stats.materials}</b><small>материалов всего</small></span><span><b>{stats.ai_today}</b><small>AI запросов</small></span><span><b>{stats.reminders}</b><small>напоминаний</small></span></div></section>}

    {recent.length > 0 && <section><div className="v1-section-head"><div><span className="v1-eyebrow">CONTINUE</span><h2>Продолжить</h2></div><button onClick={() => setPage('materials')}>Все <ChevronRight size={15}/></button></div><div className="v1-recent">{recent.map(item => <button key={item.id} onClick={() => void openMaterial(item.id)}><span className="v1-iconbox"><MaterialGlyph type={item.type}/></span><div><small>{prettyType(item.type)} · {formatDate(item.created_at)}</small><b>{item.title}</b><p>{item.summary || 'Открыть материал'}</p></div><ChevronRight size={18}/></button>)}</div></section>}

    <section><div className="v1-section-head"><div><span className="v1-eyebrow">QUICK ACTIONS</span><h2>Быстрые действия</h2></div></div><div className="v1-quick-grid">
      <Quick featured icon={<Brain/>} title="Memory" text="Спроси всё, что уже отправлял" onClick={() => setPage('materials')}/>
      <Quick featured icon={<PenLine/>} title="Написать" text="Готовый ответ в нужном тоне" onClick={() => setPage('compose')}/>
      <Quick icon={<Folder/>} title="Проекты" text="Материалы по теме" onClick={() => setPage('projects')}/>
      <Quick icon={<GitCompare/>} title="Сравнить" text="Два материала" onClick={() => setPage('compare')}/>
      <Quick icon={<Bell/>} title="Напомнить" text="Не забыть важное" onClick={() => setPage('reminders')}/>
      <Quick icon={me.owner ? <Crown/> : <Zap/>} title={me.owner ? 'OWNER' : 'Clarify PRO'} text={me.owner ? 'Unlimited access' : 'Больше возможностей'} onClick={() => setPage(me.owner ? 'profile' : 'pro')}/>
    </div></section>
  </div>
}

function Quick({ featured = false, icon, title, text, onClick }: { featured?: boolean; icon: React.ReactNode; title: string; text: string; onClick: () => void }) {
  return <button className={`v1-quick ${featured ? 'featured' : ''}`} onClick={() => { haptic(); onClick() }}><span>{icon}</span><div><b>{title}</b><small>{text}</small></div><ChevronRight size={17}/></button>
}

function IntakeSheet({ open, kind, onKind, onClose, onDone, setError }: { open: boolean; kind: IntakeKind | null; onKind: (k: IntakeKind | null) => void; onClose: () => void; onDone: (m: Material) => void; setError: (s: string) => void }) {
  const [text, setText] = useState(''), [url, setUrl] = useState(''), [file, setFile] = useState<File | null>(null), [busy, setBusy] = useState(false)
  useEffect(() => { setText(''); setUrl(''); setFile(null) }, [kind, open])
  if (!open) return null
  const options = [
    { id: 'audio' as const, icon: <Mic/>, title: 'Голос / аудио', text: 'Расшифрую и найду главное' },
    { id: 'document' as const, icon: <FileText/>, title: 'Документ', text: 'PDF, DOCX, TXT и таблицы' },
    { id: 'image' as const, icon: <ImageIcon/>, title: 'Фото / скрин', text: 'Прочитаю и объясню' },
    { id: 'link' as const, icon: <Link2/>, title: 'Ссылка', text: 'Страница или видео' },
    { id: 'text' as const, icon: <Type/>, title: 'Текст', text: 'Сообщение, заметка или переписка' },
  ]
  const submit = async (e: FormEvent) => {
    e.preventDefault(); if (!kind) return; setBusy(true); setError('')
    try {
      let item: Material
      if (kind === 'text') item = await api<Material>('/api/intake/text', { method: 'POST', body: JSON.stringify({ text: text.trim() }) })
      else if (kind === 'link') item = await api<Material>('/api/intake/link', { method: 'POST', body: JSON.stringify({ url: url.trim() }) })
      else { if (!file) return; const form = new FormData(); form.append('file', file); item = await apiForm<Material>('/api/intake/file', form) }
      onDone(item)
    } catch (err) { setError(err instanceof Error ? err.message : 'Не получилось обработать материал') }
    finally { setBusy(false) }
  }
  const selected = options.find(x => x.id === kind)
  const accept = kind === 'image' ? 'image/*' : kind === 'audio' ? 'audio/*,.ogg,.opus,.m4a,.mp3,.wav,.webm' : '.pdf,.docx,.txt,.md,.xlsx,.csv'
  return <div className="v1-sheet-backdrop" onMouseDown={e => { if (e.target === e.currentTarget && !busy) onClose() }}><section className="v1-sheet"><div className="v1-handle"/><header><div><span className="v1-eyebrow">ADD TO CLARIFY</span><h2>{selected?.title || 'Что хочешь разобрать?'}</h2></div><button onClick={onClose} disabled={busy}>×</button></header>
    {busy ? <Processing kind={kind}/> : !kind ? <div className="v1-intake-options">{options.map(o => <button key={o.id} onClick={() => onKind(o.id)}><span>{o.icon}</span><div><b>{o.title}</b><small>{o.text}</small></div><ChevronRight size={18}/></button>)}</div> : <form className="v1-intake-form" onSubmit={submit}><button type="button" className="v1-back" onClick={() => onKind(null)}><ArrowLeft size={16}/> Другой тип</button>{kind === 'text' && <textarea autoFocus rows={7} value={text} onChange={e => setText(e.target.value)} placeholder="Вставь текст…"/>}{kind === 'link' && <input autoFocus value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…"/>}{['image','document','audio'].includes(kind) && <label className={`v1-filedrop ${file ? 'selected' : ''}`}><input type="file" accept={accept} onChange={e => setFile(e.target.files?.[0] || null)}/><span>{selected?.icon}</span><b>{file ? file.name : 'Выбрать файл'}</b><small>{file ? `${Math.max(.01, file.size/1024/1024).toFixed(1)} МБ` : 'Файл загрузится прямо в Clarify'}</small></label>}<button className="v1-primary" disabled={(kind === 'text' && !text.trim()) || (kind === 'link' && !url.trim()) || (['image','document','audio'].includes(kind) && !file)}><Sparkles size={17}/> Разобрать материал</button></form>}
  </section></div>
}

function Processing({ kind }: { kind: IntakeKind | null }) {
  const audio = kind === 'audio'
  return <div className="v1-processing"><span className="v1-processing-orb"><LoaderCircle size={26}/></span><h3>Clarify разбирает материал</h3><p>{audio ? 'Для длинного аудио распознавание идёт частями параллельно.' : 'Покажем результат сразу после готовности.'}</p><div><span className="done"><Check/>Материал получен</span><span className="active"><LoaderCircle/>{audio ? 'Распознаю речь' : 'Понимаю содержание'}</span><span><i/>Выделяю главное</span><span><i/>Формирую результат</span></div></div>
}

function Materials({ items, setItems, open, setError, onAdd }: Common & { items: Material[]; setItems: (v: Material[]) => void; open: (id: number) => Promise<void>; onAdd: (kind?: IntakeKind | null) => void }) {
  const [q,setQ]=useState(''),[type,setType]=useState('all'),[loading,setLoading]=useState(false),[memoryQuestion,setMemoryQuestion]=useState(''),[memoryAnswer,setMemoryAnswer]=useState<Answer|null>(null),[asking,setAsking]=useState(false)
  useEffect(() => { const timer = window.setTimeout(async () => { setLoading(true); try { const p = new URLSearchParams({ limit:'30', type }); if(q.trim()) p.set('q',q.trim()); setItems((await api<{items:Material[]}>(`/api/materials?${p}`)).items) } catch(e){ setError(e instanceof Error?e.message:'Не удалось загрузить Memory') } finally { setLoading(false) } },220); return () => clearTimeout(timer) },[q,type,setItems,setError])
  const askMemory=async(e:FormEvent)=>{e.preventDefault();if(!memoryQuestion.trim())return;setAsking(true);setMemoryAnswer(null);try{setMemoryAnswer(await api<Answer>('/api/memory/ask',{method:'POST',body:JSON.stringify({question:memoryQuestion.trim()})}));successHaptic()}catch(err){setError(err instanceof Error?err.message:'Не удалось спросить Memory')}finally{setAsking(false)}}
  return <div className="v1-stack"><div className="v1-page-head"><div><span className="v1-eyebrow">CLARIFY MEMORY</span><h1>Твои знания</h1><p>Спроси всё, что уже отправлял Clarify.</p></div><button onClick={() => onAdd()}><Plus/></button></div>
    <form className="v1-memory-ask" onSubmit={askMemory}><span><Brain/></span><div><label>Спросить мои материалы</label><input value={memoryQuestion} onChange={e=>setMemoryQuestion(e.target.value)} placeholder="Что было про зарплату?"/></div><button disabled={asking||!memoryQuestion.trim()}>{asking?<LoaderCircle className="spin"/>:<Sparkles/>}</button></form>
    {asking&&<Loading text="Ищу только релевантные материалы…"/>}{memoryAnswer&&<div className="v1-answer"><span className="v1-eyebrow">MEMORY ANSWER</span><div className="v1-answer-text">{memoryAnswer.answer}</div><Sources items={memoryAnswer.sources} onOpen={id=>void open(id)}/></div>}
    <div className="v1-search"><Search size={18}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Поиск по Memory…"/></div><div className="v1-chips">{[['all','Все'],['documents','Документы'],['voice','Голос'],['images','Фото'],['links','Ссылки'],['text','Текст']].map(([id,label])=><button key={id} className={type===id?'active':''} onClick={()=>setType(id)}>{label}</button>)}</div>
    {loading?<SkeletonList/>:!items.length?<Empty icon={<Brain size={26}/>} title="Memory пока пустая" text="Добавь первый материал — Clarify начнёт собирать личную базу знаний." action={()=>onAdd()}/>:<div className="v1-material-list">{items.map(item=><button key={item.id} onClick={()=>void open(item.id)}><span className="v1-iconbox"><MaterialGlyph type={item.type}/></span><div><small>{prettyType(item.type)} · {formatDate(item.created_at)}</small><b>{item.title}</b><p>{item.summary||'Открыть материал'}</p></div><ChevronRight size={18}/></button>)}</div>}
  </div>
}

function MaterialDetail({ material, onDeleted, openMaterial, setError, setBusy, busy }: Common & { material: Material; onDeleted:()=>void; openMaterial:(id:number)=>Promise<void> }) {
  const [answer,setAnswer]=useState<Answer|null>(null),[question,setQuestion]=useState('')
  const actions=useMemo(()=>[
    ['summary','Кратко',<Sparkles/>],['main','Главное',<Brain/>],['tasks','Действия',<Check/>],['risks','Риски',<CircleAlert/>],['money','Деньги',<Zap/>],['dates','Сроки',<Clock3/>],['plain','Проще',<WandSparkles/>],['wants','Что хотят',<UserRound/>],
  ] as const,[])
  const run=async(action:string)=>{setBusy(true);setAnswer(null);try{setAnswer(await api<Answer>(`/api/materials/${material.id}/action`,{method:'POST',body:JSON.stringify({action})}));successHaptic()}catch(e){setError(e instanceof Error?e.message:'Не удалось выполнить действие')}finally{setBusy(false)}}
  const ask=async(e:FormEvent)=>{e.preventDefault();if(!question.trim())return;setBusy(true);setAnswer(null);try{setAnswer(await api<Answer>(`/api/materials/${material.id}/ask`,{method:'POST',body:JSON.stringify({question})}));successHaptic()}catch(err){setError(err instanceof Error?err.message:'Не удалось ответить')}finally{setBusy(false)}}
  const remove=async()=>{if(!confirm('Удалить этот материал?'))return;try{await api(`/api/materials/${material.id}`,{method:'DELETE'});onDeleted()}catch(e){setError(e instanceof Error?e.message:'Не удалось удалить')}}
  return <div className="v1-stack"><div className="v1-detail-title"><span className="v1-iconbox big"><MaterialGlyph type={material.type} size={25}/></span><div><small>{prettyType(material.type)} · {formatDate(material.created_at)}</small><h1>{material.title}</h1></div></div><section className="v1-summary"><span className="v1-eyebrow">CLARIFY SUMMARY</span><h3>Кратко</h3><p>{material.summary||'Материал сохранён. Выбери действие или задай вопрос.'}</p></section><div className="v1-action-grid">{actions.map(([id,label,icon])=><button key={id} onClick={()=>void run(id)}><span>{icon}</span><b>{label}</b></button>)}</div><form className="v1-ask" onSubmit={ask}><span className="v1-eyebrow">ASK CLARIFY</span><textarea rows={3} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Задай вопрос по этому материалу…"/><button className="v1-primary" disabled={busy||!question.trim()}><Sparkles size={17}/>{busy?'Думаю…':'Спросить'}</button></form>{busy&&<Loading text="Clarify разбирается…"/>}{answer&&<div className="v1-answer"><span className="v1-eyebrow">CLARIFY</span><div className="v1-answer-text">{answer.answer}</div><Sources items={answer.sources} onOpen={id=>void openMaterial(id)}/><div className="v1-answer-tools"><button onClick={()=>setQuestion('Сделай ответ короче')}><Zap/>Короче</button><button onClick={()=>setQuestion('Объясни ещё проще')}><WandSparkles/>Проще</button></div></div>}<details className="v1-source"><summary>Исходник</summary><pre>{material.text||'Исходник не сохранён.'}</pre></details><button className="v1-danger" onClick={()=>void remove()}><Trash2 size={17}/>Удалить материал</button></div>
}

function Projects({items,setItems,open,setError}:Common&{items:Project[];setItems:(p:Project[])=>void;open:(id:number)=>void}){const[name,setName]=useState('');const load=useCallback(async()=>{try{setItems((await api<{items:Project[]}>('/api/projects')).items)}catch(e){setError(e instanceof Error?e.message:'Не удалось загрузить проекты')}},[setItems,setError]);useEffect(()=>{void load()},[load]);const create=async(e:FormEvent)=>{e.preventDefault();if(!name.trim())return;try{await api('/api/projects',{method:'POST',body:JSON.stringify({name})});setName('');successHaptic();await load()}catch(err){setError(err instanceof Error?err.message:'Не удалось создать проект')}};return <div className="v1-stack"><div className="v1-page-head"><div><span className="v1-eyebrow">WORKSPACES</span><h1>Проекты</h1><p>Собирай связанные материалы в одной теме.</p></div></div><form className="v1-inline-create" onSubmit={create}><Folder/><input value={name} onChange={e=>setName(e.target.value)} placeholder="Например: Закупка №27"/><button><Plus/></button></form>{!items.length?<Empty icon={<Folder/>} title="Проектов пока нет" text="Создай первый проект для связанной работы."/>:<div className="v1-project-grid">{items.map(p=><button key={p.id} onClick={()=>open(p.id)}><span><Folder/></span><div><b>{p.name}</b><small>{p.count} материалов</small></div><ChevronRight/></button>)}</div>}</div>}

function ProjectDetail({project,setError,setBusy,busy,openMaterial}:Common&{project:Project;openMaterial:(id:number)=>Promise<void>}){const[question,setQuestion]=useState(''),[answer,setAnswer]=useState<Answer|null>(null);const ask=async(e:FormEvent)=>{e.preventDefault();if(!question.trim())return;setBusy(true);try{setAnswer(await api<Answer>(`/api/projects/${project.id}/ask`,{method:'POST',body:JSON.stringify({question})}))}catch(err){setError(err instanceof Error?err.message:'Ошибка')}finally{setBusy(false)}};return <div className="v1-stack"><div className="v1-detail-title"><span className="v1-iconbox big"><Folder/></span><div><small>PROJECT</small><h1>{project.name}</h1></div></div><form className="v1-ask" onSubmit={ask}><textarea rows={3} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Что мы в итоге согласовали?"/><button className="v1-primary" disabled={busy}><Sparkles/>{busy?'Собираю…':'Спросить'}</button></form>{answer&&<div className="v1-answer"><div className="v1-answer-text">{answer.answer}</div><Sources items={answer.sources} onOpen={id=>void openMaterial(id)}/></div>}<h2>Материалы</h2><div className="v1-material-list">{(project.materials||[]).map(m=><button key={m.id} onClick={()=>void openMaterial(m.id)}><span className="v1-iconbox"><MaterialGlyph type={m.type}/></span><div><b>{m.title}</b><p>{m.summary}</p></div><ChevronRight/></button>)}</div></div>}

function Compare({setError,setBusy,busy}:Common){const[items,setItems]=useState<Material[]>([]),[a,setA]=useState(''),[b,setB]=useState(''),[answer,setAnswer]=useState('');useEffect(()=>{void api<{items:Material[]}>('/api/materials?limit=50').then(d=>setItems(d.items)).catch(e=>setError(e instanceof Error?e.message:'Ошибка'))},[setError]);const run=async()=>{if(!a||!b||a===b){setError('Выбери два разных материала');return}setBusy(true);setAnswer('');try{setAnswer((await api<{answer:string}>('/api/compare',{method:'POST',body:JSON.stringify({first_id:Number(a),second_id:Number(b)})})).answer);successHaptic()}catch(e){setError(e instanceof Error?e.message:'Ошибка сравнения')}finally{setBusy(false)}};return <div className="v1-stack"><div className="v1-page-head"><div><span className="v1-eyebrow">COMPARE</span><h1>Сравнить</h1><p>Clarify найдёт важные отличия между двумя материалами.</p></div></div><div className="v1-compare"><label>Материал A<select value={a} onChange={e=>setA(e.target.value)}><option value="">Выбрать…</option>{items.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><span><GitCompare/>VS</span><label>Материал B<select value={b} onChange={e=>setB(e.target.value)}><option value="">Выбрать…</option>{items.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></label><button className="v1-primary" onClick={()=>void run()} disabled={busy}><GitCompare/>{busy?'Сравниваю…':'Сравнить материалы'}</button></div>{answer&&<div className="v1-answer"><div className="v1-answer-text">{answer}</div></div>}</div>}

function Reminders({setError}:Common){const[items,setItems]=useState<Reminder[]>([]),[text,setText]=useState(''),[when,setWhen]=useState('');const load=useCallback(async()=>{try{setItems((await api<{items:Reminder[]}>('/api/reminders')).items)}catch(e){setError(e instanceof Error?e.message:'Ошибка')}},[setError]);useEffect(()=>{void load()},[load]);const create=async(e:FormEvent)=>{e.preventDefault();if(!text.trim()||!when)return;try{await api('/api/reminders',{method:'POST',body:JSON.stringify({text,remind_at:new Date(when).toISOString()})});setText('');setWhen('');successHaptic();await load()}catch(err){setError(err instanceof Error?err.message:'Ошибка')}};const remove=async(id:number)=>{try{await api(`/api/reminders/${id}`,{method:'DELETE'});await load()}catch(e){setError(e instanceof Error?e.message:'Ошибка')}};return <div className="v1-stack"><div className="v1-page-head"><div><span className="v1-eyebrow">REMINDERS</span><h1>Напоминания</h1><p>Важное не потеряется после разбора.</p></div></div><form className="v1-reminder-form" onSubmit={create}><input value={text} onChange={e=>setText(e.target.value)} placeholder="Что напомнить?"/><input type="datetime-local" value={when} onChange={e=>setWhen(e.target.value)}/><button className="v1-primary"><Bell/>Создать</button></form>{!items.length?<Empty icon={<Bell/>} title="Нет активных напоминаний" text="Создай первое — Clarify напомнит вовремя."/>:<div className="v1-reminders">{items.map(r=><div key={r.id}><span><Bell/></span><div><b>{r.text}</b><small>{formatDate(r.remind_at)}</small></div><button onClick={()=>void remove(r.id)}><Trash2/></button></div>)}</div>}</div>}

function Compose({setError,setBusy,busy}:Common){const[brief,setBrief]=useState(''),[answer,setAnswer]=useState('');const presets=['Ответить человеку','Вежливее','Короче','Увереннее','Деловой стиль','Дружелюбнее'];const run=async(e:FormEvent)=>{e.preventDefault();if(!brief.trim())return;setBusy(true);try{setAnswer((await api<{answer:string}>('/api/compose',{method:'POST',body:JSON.stringify({brief})})).answer);successHaptic()}catch(err){setError(err instanceof Error?err.message:'Ошибка')}finally{setBusy(false)}};const rewrite=async(mode:string)=>{if(!answer)return;setBusy(true);try{setAnswer((await api<{answer:string}>('/api/rewrite',{method:'POST',body:JSON.stringify({text:answer,mode})})).answer)}catch(e){setError(e instanceof Error?e.message:'Ошибка')}finally{setBusy(false)}};const copy=async()=>{if(!answer)return;await navigator.clipboard.writeText(answer);successHaptic()};return <div className="v1-stack"><div className="v1-ai-head"><span><Sparkles/></span><span className="v1-eyebrow">WRITE WITH CLARIFY</span><h1>Что написать за тебя?</h1><p>Опиши смысл как получится. Clarify превратит его в готовый текст.</p></div><div className="v1-preset-row">{presets.map(p=><button key={p} onClick={()=>setBrief(v=>v?`${v}\n${p.toLowerCase()}`:p)}>{p}</button>)}</div><form className="v1-compose" onSubmit={run}><textarea rows={7} value={brief} onChange={e=>setBrief(e.target.value)} placeholder="Поставщику: товар нужен до пятницы, спроси, успеет ли он…"/><button className="v1-primary" disabled={busy||!brief.trim()}><PenLine/>{busy?'Пишу…':'Написать'}</button></form>{busy&&<Loading text="Подбираю формулировку…"/>}{answer&&<><div className="v1-answer selectable"><span className="v1-eyebrow">READY TO SEND</span><div className="v1-answer-text">{answer}</div><button className="v1-copy" onClick={()=>void copy()}><Copy/>Скопировать</button></div><div className="v1-rewrite">{[['мягче и теплее','Мягче'],['официальнее','Официальнее'],['максимально короче','Короче'],['убедительнее','Увереннее'],['другой вариант','Другой вариант']].map(([mode,label])=><button key={mode} onClick={()=>void rewrite(mode)}>{label}</button>)}</div></>}</div>}

function Pro({me,setError,refreshMe}:Common&{refreshMe:()=>Promise<void>}){const[loading,setLoading]=useState(false);const buy=async()=>{setLoading(true);try{const r=await api<{invoice_url:string}>('/api/pro/invoice',{method:'POST'});openInvoice(r.invoice_url,()=>void refreshMe())}catch(e){setError(e instanceof Error?e.message:'Не удалось открыть оплату')}finally{setLoading(false)}};if(me.owner)return <div className="v1-owner"><Crown/><span className="v1-eyebrow">CLARIFY OWNER</span><h1>Unlimited</h1><p>Клиентские лимиты отключены.</p></div>;return <div className="v1-stack"><section className="v1-pro"><Sparkles/><span className="v1-eyebrow">CLARIFY PRO</span><h1>Больше Clarify.<br/>Меньше ограничений.</h1><p>Для ежедневной работы с документами, голосовыми и Memory.</p><strong>{me.pro_price} ⭐ <small>/ 30 дней</small></strong><button className="v1-primary" disabled={loading||me.plan==='PRO'} onClick={()=>void buy()}>{me.plan==='PRO'?'PRO уже активен':loading?'Открываю Stars…':'Подключить PRO'}</button></section></div>}

function Profile({me,setError,refreshMe,setPage}:Common&{refreshMe:()=>Promise<void>}){const[timezone,setTimezone]=useState(me.timezone),[style,setStyle]=useState(me.style||''),[mode,setMode]=useState(me.ai_mode||'fast'),[saving,setSaving]=useState(false),[stats,setStats]=useState<Stats|null>(null),[confirmErase,setConfirmErase]=useState(false);useEffect(()=>{void api<Stats>('/api/profile/stats').then(setStats).catch(()=>undefined)},[]);const save=async()=>{setSaving(true);try{await api('/api/settings',{method:'PATCH',body:JSON.stringify({timezone,style,ai_mode:mode})});successHaptic();await refreshMe()}catch(e){setError(e instanceof Error?e.message:'Не удалось сохранить')}finally{setSaving(false)}};const erase=async()=>{try{await api('/api/me/data',{method:'DELETE'});setConfirmErase(false);successHaptic();await refreshMe()}catch(e){setError(e instanceof Error?e.message:'Ошибка')}};const limit=me.usage.limit;const percent=limit?Math.min(100,Math.round(me.usage.used/Math.max(1,limit)*100)):0;return <div className="v1-stack"><section className="v1-profile-card"><div className="v1-avatar">{(me.first_name||'C')[0].toUpperCase()}</div><div><small>{me.username?`@${me.username}`:'Telegram user'}</small><h1>{me.first_name||'Clarify User'}</h1><b>{me.owner?<><Crown/> OWNER · Unlimited</>:me.plan}</b></div></section><div className="v1-stats"><span><FileText/><small>Материалы</small><b>{stats?.materials??'—'}</b></span><span><Folder/><small>Проекты</small><b>{stats?.projects??'—'}</b></span><span><Sparkles/><small>AI сегодня</small><b>{stats?.ai_today??me.usage.used}</b></span></div><section className="v1-usage"><span className="v1-eyebrow">TODAY</span><h3>AI использование</h3>{me.owner?<div className="v1-unlimited"><Crown/>Unlimited<small>Лимиты отключены для OWNER</small></div>:<><p>{me.usage.used} из {limit??'∞'} запросов</p><div className="v1-track"><i style={{width:`${percent}%`}}/></div>{me.plan==='FREE'&&<button onClick={()=>setPage('pro')}>Увеличить лимиты <ChevronRight/></button>}</>}</section><section className="v1-settings"><span className="v1-eyebrow">PREFERENCES</span><label>Часовой пояс<select value={timezone} onChange={e=>setTimezone(e.target.value)}><option>Europe/Moscow</option><option>Europe/Prague</option><option>Europe/Berlin</option><option>UTC</option></select></label><label>Стиль ответов<textarea rows={3} value={style} onChange={e=>setStyle(e.target.value)} placeholder="Коротко, разговорно, без канцелярита"/></label><label>AI режим<div className="v1-segmented"><button className={mode==='fast'?'active':''} onClick={()=>setMode('fast')} type="button"><Zap/>Быстро</button><button className={mode==='smart'?'active':''} onClick={()=>setMode('smart')} type="button"><Brain/>Умно</button></div></label><button className="v1-primary" disabled={saving} onClick={()=>void save()}><Settings2/>{saving?'Сохраняю…':'Сохранить настройки'}</button></section><section className="v1-privacy"><h3>Приватность</h3><p>Материалы, проекты, настройки и AI-историю можно удалить в любой момент.</p><button className="v1-danger" onClick={()=>setConfirmErase(true)}><Trash2/>Удалить мои данные</button></section><div className="v1-version">CLARIFY {me.version}</div>{confirmErase&&<ConfirmErase onCancel={()=>setConfirmErase(false)} onConfirm={()=>void erase()}/>}</div>}

function ConfirmErase({onCancel,onConfirm}:{onCancel:()=>void;onConfirm:()=>void}){return <div className="v1-modal-backdrop"><div className="v1-modal"><span><Trash2/></span><h3>Удалить все данные Clarify?</h3><p>Будут удалены материалы, проекты, напоминания, настройки и AI-история. Это действие нельзя отменить.</p><div><button onClick={onCancel}>Отмена</button><button className="danger" onClick={onConfirm}>Удалить всё</button></div></div></div>}

function Onboarding({onDone}:{onDone:()=>void}){const[step,setStep]=useState(0);const slides=[{icon:<Sparkles/>,eyebrow:'WELCOME',title:'Clarify 1.0',text:'AI Workspace для понимания информации без лишней рутины.'},{icon:<Plus/>,eyebrow:'SEND ANYTHING',title:'Добавляй что угодно',text:'Голосовые, документы, скриншоты, ссылки и обычный текст.'},{icon:<Brain/>,eyebrow:'GET CLARITY',title:'Clarify запоминает',text:'Memory помогает возвращаться к знаниям и задавать новые вопросы.'}];const s=slides[step];return <div className="v1-onboarding"><section><button className="skip" onClick={onDone}>Пропустить</button><span className="orb">{s.icon}</span><span className="v1-eyebrow">{s.eyebrow}</span><h1>{s.title}</h1><p>{s.text}</p><div className="dots">{slides.map((_,i)=><i key={i} className={i===step?'active':''}/>)}</div><button className="v1-primary" onClick={()=>step<slides.length-1?setStep(step+1):onDone()}>{step<slides.length-1?'Дальше':'Начать'}<ChevronRight/></button></section></div>}

export default AppV1
