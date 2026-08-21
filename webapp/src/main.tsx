import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppV1'
import CopilotWidget from './CopilotWidget'
import SupportWidget from './SupportWidget'
import PlansWidget from './PlansWidget'
import MaterialCleanupWidget from './MaterialCleanupWidget'
import ProfileShortcutWidget from './ProfileShortcutWidget'
import './v1.css'
import './v1-mobile.css'
import './support.css'
import './plans.css'
import './plan-badge.css'
import './product-upgrade.css'
import './copilot.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <ProfileShortcutWidget />
    <PlansWidget />
    <MaterialCleanupWidget />
    <CopilotWidget />
    <SupportWidget />
  </StrictMode>,
)
