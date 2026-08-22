import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppV1'
import CopilotWidget from './CopilotWidget'
import SupportWidget from './SupportWidget'
import PlansWidget from './PlansWidget'
import MaterialCleanupWidget from './MaterialCleanupWidget'
import ProfileShortcutWidget from './ProfileShortcutWidget'
import UXFixesWidget from './UXFixesWidget'
import './v1.css'
import './v1-mobile.css'
import './support.css'
import './plans.css'
import './plan-badge.css'
import './product-upgrade.css'
import './copilot.css'
import './ux-fixes.css'

const telegramWebApp = window.Telegram?.WebApp

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <ProfileShortcutWidget />
    <PlansWidget />
    <MaterialCleanupWidget />
    <CopilotWidget />
    <UXFixesWidget />
    <SupportWidget />
  </StrictMode>,
)

// Tell Telegram that the UI is ready and request the full available height.
// This is intentionally done for every entry path, including reply-keyboard WebApps.
telegramWebApp?.expand?.()
telegramWebApp?.ready?.()
