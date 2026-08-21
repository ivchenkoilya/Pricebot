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
  const [hasImage, setHasImage] = useState(false)

  useEffect(() => {
    if (!hasTelegramAuth()) return
    const scan = () => {
      const detailTitle = document.querySelector('.v1-detail-title h1')?.textContent?.trim() || ''
      const details = document.querySelector('.v1-source')
      setSourceTitle(detailTitle)
      setSourceHost(ensureSourceHost(details))
    }
    scan()
    const observer = new MutationObserver(scan)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setHasImage(false)
  }, [sourceTitle, sourceHost])

  useEffect(() => {
    const details = sourceHost?.closest('.v1-source')
    if (!details) return
    details.classList.toggle('has-source-image', hasImage)
    return () => details.classList.remove('has-source-image')
  }, [sourceHost, hasImage])

  if (!hasTelegramAuth() || !sourceHost || !sourceTitle) return null
  return createPortal(<SourceImagePreview title={sourceTitle} onAvailable={setHasImage} />, sourceHost)
}

function SourceImagePreview({ title, onAvailable }: { title: string; onAvailable: (value: boolean) => void }) {
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
        const image = search.items.find(item =>
          item.title.trim() === title.trim() && ['image', 'screenshot'].includes(item.type),
        )
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
  }, [title, onAvailable])

  if (!loading && !url) return null
  return <div className="clarify-source-media">
    {loading ? <div className="clarify-source-media-loading"><LoaderCircle className="spin" /><span>Загружаю оригинал…</span></div> : <>
      <div className="clarify-source-media-label"><ImageIcon size={16} /><span>Оригинальное изображение</span></div>
      <img src={url} alt="Исходное изображение" />
    </>}
  </div>
}
