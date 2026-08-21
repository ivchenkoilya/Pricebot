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

async function request<T>(path: string, init: RequestInit = {}, json = true): Promise<T> {
  const initData = tg()?.initData || ''
  const headers = new Headers(init.headers || {})
  if (json && init.body !== undefined) headers.set('Content-Type', 'application/json')
  if (initData) headers.set('Authorization', `tma ${initData}`)
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let message = 'Не получилось выполнить действие'
    try {
      const body = await response.json()
      if (body?.detail) message = String(body.detail)
    } catch {
      // keep friendly fallback
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
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