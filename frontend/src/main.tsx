import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App'
import { initLang } from './i18n'
import { initMotion, initReveal, initSpotlight, initTheme } from './ui'

initTheme()
initSpotlight()
initMotion()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)

initReveal()
initLang()
