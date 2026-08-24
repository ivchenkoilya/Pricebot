import { Component, StrictMode, type ErrorInfo, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppV1'
import BetaNoticeWidget from './BetaNoticeWidget'
import CopilotWidget from './CopilotWidget'
import DeepLinkWidget from './DeepLinkWidget'
import SupportWidget from './SupportWidget'
import PlansWidget from './PlansWidget'
import MaterialCleanupWidget from './MaterialCleanupWidget'
import ProfileShortcutWidget from './ProfileShortcutWidget'
import ReferralProfileWidget from './ReferralProfileWidget'
import RussianUiWidget from './RussianUiWidget'
import UXFixesWidget from './UXFixesWidget'
import './v1.css'
import './v1-mobile.css'
import './support.css'
import './beta-notice.css'
import './plans.css'
import './plan-badge.css'
import './product-upgrade.css'
import './copilot.css'
import './referral.css'
import './ux-fixes.css'

const telegramWebApp = window.Telegram?.WebApp

// Mark the page ready before React mounts. On some Telegram Android launches
// from persistent reply-keyboard WebApp buttons the WebView waits for ready()
// while React is still booting, leaving only the background visible.
telegramWebApp?.ready?.()
telegramWebApp?.expand?.()
telegramWebApp?.setHeaderColor?.('#061126')
telegramWebApp?.setBackgroundColor?.('#061126')

class MiniAppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Clarify Mini App render failed', error, info)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return <main className="v1-outside">
      <div>
        <h2>Не получилось открыть Clarify</h2>
        <p>Интерфейс не загрузился. Попробуй перезапустить мини-приложение — данные не потеряются.</p>
        <button className="v1-primary" onClick={() => window.location.reload()}>Открыть заново</button>
      </div>
    </main>
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MiniAppErrorBoundary>
      <App />
      <ProfileShortcutWidget />
      <ReferralProfileWidget />
      <PlansWidget />
      <MaterialCleanupWidget />
      <CopilotWidget />
      <UXFixesWidget />
      <DeepLinkWidget />
      <BetaNoticeWidget />
      <SupportWidget />
      <RussianUiWidget />
    </MiniAppErrorBoundary>
  </StrictMode>,
)
