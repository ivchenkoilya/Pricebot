import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppV1'
import SupportWidget from './SupportWidget'
import './v1.css'
import './v1-mobile.css'
import './support.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <SupportWidget />
  </StrictMode>,
)
