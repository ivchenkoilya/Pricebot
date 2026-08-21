import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Image as ImageIcon, LoaderCircle } from 'lucide-react'
import { api, hasTelegramAuth } from './api'

type SearchItem = {
  id: number
  type: string
  title: string
  created_at?: string | null
}

type SearchResult = { items: SearchItem[] }

const formatDate = (value?: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function ensureSourceHost(details: Element | null) {
  if (!details) return null
  let host = details.querySelector('#clarify-source-media-host') as HTMLElement | null
  if (!host) {
    host = document.createElement('div')
    host.id = 'clarify-source-media-host'
    const textSource = details.querySelector('pre')
    if (textSource) details.insertBefore(host, textSource)
    else details.appendChild(host)
  }
  return host
}

function useAiAnswerAutoScroll() {
  useEffect(() => {
    if (!hasTelegramAuth()) return
    let lastSignature = ''
    let timer = 0

    const scan = () => {
      const aiHead = document.querySelector('.v1-ai-head')
      if (!aiHead) {
        lastSignature = ''
        return
      }
      const page = aiHead.closest('.v1-stack')
      const answer = page?.querySelector('.v1-answer.selectable') as HTMLElement | null
      const text = answer?.querySelector('.v1-answer-text')?.textContent?.trim() || ''
      if (!answer || !text || text === lastSignature) return

      lastSignature = text
      window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        answer.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 120)
    }

    scan()
    const observer = new MutationObserver(scan)
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    return () => {
      observer.disconnect()
      window.clearTimeout(timer)
    }
  }, [])
}

export default function UXFixesWidget() {
  useAiAnswerAutoScroll()
  const [sourceHost, setSourceHost] = useState<HTMLElement | null>(null)
  const [sourceTitle, setSourceTitle] = useState('')
  const [sourceMeta, setSourceMeta] = useState('')
  const [hasImage, setHasImage] = useState(false)

  useEffect(() => {
    if (!hasTelegramAuth()) return
    const scan = () => {
      const detail = document.querySelector('.v1-detail-title')
      const detailTitle = detail?.querySelector('h1')?.textContent?.trim() || ''
      const detailMeta = detail?.querySelector('small')?.textContent?.trim() || ''
      const details = document.querySelector('.v1-source')
      setSourceTitle(detailTitle)
      setSourceMeta(detailMeta)
      setSourceHost(ensureSourceHost(details))
    }
    scan()
    const observer = new MutationObserver(scan)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setHasImage(false)
  }, [sourceTitle, sourceMeta, sourceHost])

  useEffect(() => {
    const details = sourceHost?.closest('.v1-source')
    if (!details) return
    details.classList.toggle('has-source-image', hasImage)
    return () => details.classList.remove('has-source-image')
  }, [sourceHost, hasImage])

  if (!hasTelegramAuth() || !sourceHost || !sourceTitle) return null
  return createPortal(
    <SourceImagePreview title={sourceTitle} meta={sourceMeta} onAvailable={setHasImage} />,
    sourceHost,
  )
}

function SourceImagePreview({ title, meta, onAvailable }: { title: string; meta: string; onAvailable: (value: boolean) => void }) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    let objectUrl = ''
    onAvailable(false)
    setUrl('')
    setLoading(true)

    const load = async () => {
      try {
        const search = await api<SearchResult>(`/api/copilot/search?q=${encodeURIComponent(title)}&limit=8`)
        if (!alive) return
        const exactImages = search.items.filter(item =>
          item.title.trim() === title.trim() && ['image', 'screenshot'].includes(item.type),
        )
        const image = exactImages.find(item => {
          const renderedDate = formatDate(item.created_at)
          return renderedDate && meta.includes(renderedDate)
        }) || exactImages[0]
        if (!image) {
          setLoading(false)
          return
        }

        const initData = window.Telegram?.WebApp.initData || ''
        const headers = new Headers()
        if (initData) headers.set('Authorization', `tma ${initData}`)
        const response = await fetch(`/api/materials/${image.id}/source-image`, { headers })
        if (!alive) return
        if (response.status === 404) {
          setLoading(false)
          return
        }
        if (!response.ok) throw new Error('source image unavailable')
        const blob = await response.blob()
        if (!alive) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
        setLoading(false)
        onAvailable(true)
      } catch {
        if (alive) setLoading(false)
      }
    }

    void load()
    return () => {
      alive = false
      onAvailable(false)
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [title, meta, onAvailable])

  if (!loading && !url) return null
  return <div className="clarify-source-media">
    {loading ? <div className="clarify-source-media-loading"><LoaderCircle className="spin" /><span>Загружаю оригинал…</span></div> : <>
      <div className="clarify-source-media-label"><ImageIcon size={16} /><span>Оригинальное изображение</span></div>
      <img src={url} alt="Исходное изображение" />
    </>}
  </div>
}
