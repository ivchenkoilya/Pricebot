import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppV1'
import BetaNoticeWidget from './BetaNoticeWidget'
import CopilotWidget from './CopilotWidget'
import SupportWidget from './SupportWidget'
import PlansWidget from './PlansWidget'
import MaterialCleanupWidget from './MaterialCleanupWidget'
import ProfileShortcutWidget from './ProfileShortcutWidget'
import ReferralProfileWidget from './ReferralProfileWidget'
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <ProfileShortcutWidget />
    <ReferralProfileWidget />
    <PlansWidget />
    <MaterialCleanupWidget />
    <CopilotWidget />
    <UXFixesWidget />
    <BetaNoticeWidget />
    <SupportWidget />
  </StrictMode>,
)
