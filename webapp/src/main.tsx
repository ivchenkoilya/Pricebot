import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import LaunchApp from './LaunchApp'
import './launch.css'

const telegramWebApp = window.Telegram?.WebApp

// Render the product shell immediately; account and material data load in parallel.
telegramWebApp?.ready?.()
telegramWebApp?.expand?.()
telegramWebApp?.setHeaderColor?.('#061126')
telegramWebApp?.setBackgroundColor?.('#061126')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LaunchApp />
  </StrictMode>,
)
