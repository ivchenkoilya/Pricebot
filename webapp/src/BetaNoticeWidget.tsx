import { useState } from 'react'
import { LifeBuoy, X } from 'lucide-react'
import { haptic, hasTelegramAuth } from './api'

const STORAGE_KEY = 'clarify_beta_notice_v1'

export default function BetaNoticeWidget() {
  const [visible, setVisible] = useState(() => window.localStorage.getItem(STORAGE_KEY) !== 'dismissed')

  if (!hasTelegramAuth() || !visible) return null

  const dismiss = () => {
    window.localStorage.setItem(STORAGE_KEY, 'dismissed')
    setVisible(false)
  }

  const openSupport = () => {
    haptic()
    window.dispatchEvent(new CustomEvent('clarify:open-support'))
  }

  return <aside className="beta-notice" role="status">
    <div className="beta-notice-icon">🧪</div>
    <div className="beta-notice-copy">
      <b>Clarify пока в разработке</b>
      <span>Некоторые функции могут работать нестабильно. Если заметишь проблему — напиши в поддержку.</span>
      <button onClick={openSupport}><LifeBuoy /> Поддержка</button>
    </div>
    <button className="beta-notice-close" aria-label="Скрыть уведомление" onClick={dismiss}><X /></button>
  </aside>
}
