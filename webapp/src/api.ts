export type Material = {
  id: number
  type: string
  title: string
  summary: string
  status: string
  created_at: string | null
  text?: string
}

export type Me = {
  telegram_id: number
  first_name: string
  username?: string | null
  owner: boolean
  plan: 'OWNER' | 'MAX' | 'PRO' | 'FREE'
  pro_until?: string | null
  usage: { used: number; limit: number | null; bonus?: number }
  timezone: string
  style: string
  ai_mode: 'fast' | 'smart'
  version: string
  pro_price: number
  max_price?: number
}

const tg = () => window.Telegram?.WebApp

export function hasTelegramAuth() {
  return Boolean(tg()?.initData)
}

function localizeText(value: string) {
  return value
    .replaceAll('Memory', 'Материалы')
    .replaceAll('Smart AI', 'Умный AI')
    .replaceAll('Fast AI', 'Быстрый AI')
    .replaceAll('AI Inbox', 'Важное')
}

function localizePayload<T>(path: string, payload: T): T {
  if (path !== '/api/plans' || !payload || typeof payload !== 'object') return payload
  const raw = payload as unknown as {
    plans?: Array<{ tagline?: string; features?: string[] }>
    note?: string
  }
  raw.plans?.forEach(plan => {
    if (plan.tagline) plan.tagline = localizeText(plan.tagline)
    if (plan.features) plan.features = plan.features.map(localizeText)
  })
  if (raw.note) raw.note = localizeText(raw.note)
  return payload
}

function requestTimeout(path: string, method: string) {
  if (path.startsWith('/api/analytics/')) return 6_000
  if (path === '/api/intake/file') return 420_000
  if (path.startsWith('/api/intake/')) return 150_000
  if (path.includes('/ask') || path.includes('/action') || path.includes('/full') || path === '/api/compose' || path === '/api/rewrite') return 150_000
  return method === 'GET' ? 30_000 : 90_000
}

async function sleep(ms: number) {
  await new Promise(resolve => window.setTimeout(resolve, ms))
}

async function request<T>(path: string, init: RequestInit = {}, json = true): Promise<T> {
  const initData = tg()?.initData || ''
  const headers = new Headers(init.headers || {})
  if (json && init.body !== undefined) headers.set('Content-Type', 'application/json')
  if (initData) headers.set('Authorization', `tma ${initData}`)

  const method = (init.method || 'GET').toUpperCase()
  // Only idempotent reads are retried. POSTing an AI request twice could cost
  // tokens or create duplicate materials, so writes never retry automatically.
  const attempts = method === 'GET' ? 2 : 1
  let lastError: unknown = null

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), requestTimeout(path, method))
    try {
      const response = await fetch(path, { ...init, headers, signal: controller.signal })
      if (!response.ok) {
        let message = 'Не получилось выполнить действие'
        try {
          const body = await response.json()
          if (body?.detail) message = localizeText(String(body.detail))
        } catch {
          // keep friendly fallback
        }
        if (method === 'GET' && attempt + 1 < attempts && response.status >= 500) {
          await sleep(350)
          continue
        }
        throw new Error(message)
      }
      const payload = await response.json() as T
      return localizePayload(path, payload)
    } catch (error) {
      lastError = error
      if (error instanceof DOMException && error.name === 'AbortError') {
        if (attempt + 1 < attempts) {
          await sleep(350)
          continue
        }
        throw new Error('Сервис отвечает слишком долго. Попробуй ещё раз.')
      }
      if (error instanceof Error && error.message !== 'Failed to fetch') throw error
      if (attempt + 1 < attempts) {
        await sleep(350)
        continue
      }
    } finally {
      window.clearTimeout(timer)
    }
  }

  if (lastError instanceof Error && lastError.message && lastError.message !== 'Failed to fetch') throw lastError
  throw new Error('Нет связи с Clarify. Проверь интернет и попробуй ещё раз.')
}

export function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return request<T>(path, init, true)
}

export function apiForm<T>(path: string, form: FormData, init: RequestInit = {}): Promise<T> {
  return request<T>(path, { ...init, method: init.method || 'POST', body: form }, false)
}

export function haptic(type: 'light' | 'medium' | 'heavy' = 'light') {
  tg()?.HapticFeedback?.impactOccurred?.(type)
}

export function successHaptic() {
  tg()?.HapticFeedback?.notificationOccurred?.('success')
}

export function closeToChat() {
  tg()?.close()
}

export type InvoiceStatus = 'paid' | 'cancelled' | 'failed' | 'pending' | 'opened' | string

/**
 * Open a Telegram Stars invoice with fallbacks for older Android WebViews.
 * Returns true once an opening method was invoked. The status callback is also
 * useful for showing immediate UI feedback instead of making a payment button
 * feel like a no-op.
 */
export function openInvoice(
  url: string,
  onDone?: () => void,
  onStatus?: (status: InvoiceStatus) => void,
): boolean {
  const webapp = tg()
  const finish = (status: string) => {
    onStatus?.(status)
    if (status === 'paid') onDone?.()
  }

  try {
    if (webapp?.openInvoice) {
      webapp.openInvoice(url, finish)
      onStatus?.('opened')
      return true
    }

    const wa = webapp as unknown as {
      openTelegramLink?: (link: string) => void
      openLink?: (link: string) => void
    } | undefined

    if (url.startsWith('https://t.me/') && wa?.openTelegramLink) {
      wa.openTelegramLink(url)
      onStatus?.('opened')
      return true
    }
    if (wa?.openLink) {
      wa.openLink(url)
      onStatus?.('opened')
      return true
    }

    window.location.assign(url)
    onStatus?.('opened')
    return true
  } catch {
    try {
      window.location.assign(url)
      onStatus?.('opened')
      return true
    } catch {
      onStatus?.('failed')
      return false
    }
  }
}
