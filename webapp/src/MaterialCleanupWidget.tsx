import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Trash2, X } from 'lucide-react'
import { api, haptic, hasTelegramAuth, successHaptic } from './api'

export default function MaterialCleanupWidget() {
  const [target, setTarget] = useState<HTMLElement | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [deleted, setDeleted] = useState<number | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!hasTelegramAuth()) return
    const find = () => {
      const active = document.querySelector('.v1-dock button.active small')?.textContent?.trim()
      setTarget(active === 'Memory' ? document.querySelector('.v1-chips') as HTMLElement | null : null)
    }
    find()
    const observer = new MutationObserver(find)
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])

  if (!hasTelegramAuth()) return null

  const removeAll = async () => {
    setBusy(true); setError('')
    try {
      const result = await api<{ ok: boolean; deleted: number }>('/api/materials', { method: 'DELETE' })
      successHaptic(); setDeleted(result.deleted)
      window.setTimeout(() => window.location.reload(), 900)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить материалы')
    } finally {
      setBusy(false)
    }
  }

  const chip = target ? createPortal(
    <button className="memory-clear-chip" onClick={() => { haptic(); setConfirming(true); setDeleted(null); setError('') }}><Trash2 /> Очистить</button>,
    target,
  ) : null

  return <>
    {chip}
    {confirming && <div className="cleanup-backdrop">
      <section className="cleanup-modal">
        <button className="cleanup-close" onClick={() => !busy && setConfirming(false)}><X /></button>
        {deleted !== null ? <div className="cleanup-success"><span><Check /></span><h3>Memory очищена</h3><p>Удалено материалов: {deleted}. Обновляю список…</p></div> : <>
          <span className="cleanup-icon"><Trash2 /></span>
          <h3>Удалить все материалы?</h3>
          <p>Будет полностью очищена Memory. Материалы исчезнут и из проектов. Настройки, тариф и напоминания останутся.</p>
          {error && <div className="cleanup-error">{error}</div>}
          <div className="cleanup-actions"><button onClick={() => setConfirming(false)} disabled={busy}>Отмена</button><button className="danger" onClick={() => void removeAll()} disabled={busy}>{busy ? 'Удаляю…' : 'Удалить всё'}</button></div>
        </>}
      </section>
    </div>}
  </>
}
