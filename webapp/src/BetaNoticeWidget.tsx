import { useState } from 'react'
import { haptic, hasTelegramAuth } from './api'

export default function BetaNoticeWidget() {
  // The warning is intentionally session-scoped: every fresh Mini App launch
  // reminds the user that Clarify is still under active development.
  const [visible, setVisible] = useState(true)

  if (!hasTelegramAuth() || !visible) return null

  const accept = () => {
    haptic('medium')
    setVisible(false)
    // After the warning closes, draw attention to the real support button
    // without opening the form automatically.
    window.setTimeout(() => {
      window.dispatchEvent(new CustomEvent('clarify:highlight-support'))
    }, 120)
  }

  return <div className="beta-gate" role="dialog" aria-modal="true" aria-labelledby="clarify-beta-title">
    <section className="beta-gate-content">
      <div className="beta-gate-icon" aria-hidden="true">🧪</div>
      <span className="beta-gate-eyebrow">BETA · ACTIVE DEVELOPMENT</span>
      <h1 id="clarify-beta-title">Clarify всё ещё находится в разработке</h1>
      <p>
        Мы только начинаем развивать Clarify и во многом опираемся на обратную связь пользователей.
        Если что-то работает не так, долго загружается, отвечает неточно или вам просто не хватает какой-то функции — напишите нам в поддержку.
        Каждое сообщение помогает нам находить проблемы, улучшать Clarify и выпускать обновления быстрее.
      </p>
      <div className="beta-gate-support-hint">🛟 Нашли проблему? Напишите в поддержку — после входа кнопка будет подсвечена.</div>
      <button className="beta-gate-accept" onClick={accept}>Хорошо</button>
    </section>
  </div>
}
