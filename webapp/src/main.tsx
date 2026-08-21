import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './AppV1'
import './v1.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
