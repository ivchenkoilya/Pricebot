import { FormEvent, useState, type ReactNode } from 'react'
import { Bug, Check, Image as ImageIcon, LifeBuoy, Lightbulb, MessageCircle, Send, X } from 'lucide-react'
import { api, apiForm, haptic, hasTelegramAuth, successHaptic } from './api'

type Kind = 'bug' | 'idea' | 'question' | 'other'

const options: Array<{ id: Kind; icon: ReactNode; title: string; text: string }> = [
  { id: 'bug', icon: <Bug />, title: 'Сообщить об ошибке', text: 'Что сломалось или работает не так' },
  { id: 'idea', icon: <Lightbulb />, title: 'Предложить идею', text: 'Что стоит добавить или улучшить' },
  { id: 'question', icon: <LifeBuoy />, title: 'Нужна помощь', text: 'Вопрос по работе Clarify' },
  { id: 'other', icon: <MessageCircle />, title: 'Другое', text: 'Любое сообщение в поддержку' },
]

export default function SupportWidget() {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<Kind>('bug')
  const [message, setMessage] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  if (!hasTelegramAuth()) return null

  const close = () => {
    if (busy) return
    setOpen(false)
    setError('')
  }

  const reset = () => {
    setMessage('')
    setFile(null)
    setSent(false)
    setError('')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (message.trim().length < 2) return
    setBusy(true)
    setError('')
    try {
      const activeLabel = document.querySelector('.v1-dock button.active small')?.textContent?.trim()
      const page = activeLabel ? `Mini App · ${activeLabel}` : 'Telegram Mini App'
      if (file) {
        const form = new FormData()
        form.append('kind', kind)
        form.append('message', message.trim())
        form.append('page', page)
        form.append('file', file)
        await apiForm('/api/support/file', form)
      } else {
        await api('/api/support', {
          method: 'POST',
          body: JSON.stringify({ kind, message: message.trim(), page }),
        })
      }
      successHaptic()
      setSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не получилось отправить обращение')
    } finally {
      setBusy(false)
    }
  }

  return <>
    {!open && <button className="support-fab" aria-label="Поддержка" onClick={() => { haptic(); reset(); setOpen(true) }}>
      <LifeBuoy /><span>Поддержка</span>
    </button>}

    {open && <div className="support-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close() }}>
      <section className="support-sheet">
        <div className="support-handle" />
        <header>
          <div><small>CLARIFY SUPPORT</small><h2>Связаться с поддержкой</h2></div>
          <button onClick={close} aria-label="Закрыть"><X /></button>
        </header>

        {sent ? <div className="support-success">
          <span><Check /></span>
          <h3>Отправлено</h3>
          <p>Поддержка получила сообщение. Когда тебе ответят, ответ придёт прямо в чат с Clarify — там можно продолжить диалог.</p>
          <button className="support-primary" onClick={close}>Готово</button>
        </div> : <form onSubmit={submit}>
          <div className="support-kinds">
            {options.map(option => <button type="button" key={option.id} className={kind === option.id ? 'active' : ''} onClick={() => { haptic(); setKind(option.id) }}>
              <span>{option.icon}</span><div><b>{option.title}</b><small>{option.text}</small></div>
            </button>)}
          </div>

          <label className="support-message">
            <span>Сообщение</span>
            <textarea rows={5} value={message} onChange={e => setMessage(e.target.value)} placeholder={kind === 'bug' ? 'Что произошло? Что ты нажал и что ожидал увидеть?' : 'Напиши сообщение…'} />
          </label>

          <label className={`support-file ${file ? 'selected' : ''}`}>
            <input type="file" accept="image/*" onChange={e => setFile(e.target.files?.[0] || null)} />
            <ImageIcon />
            <div><b>{file ? file.name : 'Добавить скриншот'}</b><small>{file ? `${Math.max(.01, file.size / 1024 / 1024).toFixed(1)} МБ` : 'Необязательно · до 8 МБ'}</small></div>
            {file && <button type="button" onClick={e => { e.preventDefault(); e.stopPropagation(); setFile(null) }}><X /></button>}
          </label>

          {error && <div className="support-error">{error}</div>}
          <button className="support-primary" disabled={busy || message.trim().length < 2}>
            <Send /> {busy ? 'Отправляю…' : 'Отправить в поддержку'}
          </button>
        </form>}
      </section>
    </div>}
  </>
}
