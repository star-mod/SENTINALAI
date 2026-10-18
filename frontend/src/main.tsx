import React, { useCallback, useState } from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import App from './App'
import { SplashScreen, Login } from './components/authscreens'

const SESSION_KEY = 'sentinelai_session'

function readSession(): boolean {
  try { return window.sessionStorage.getItem(SESSION_KEY) === '1' } catch { return false }
}

function Root() {
  const [splash, setSplash] = useState(true)
  const [authed, setAuthed] = useState(readSession)
  const finishSplash = useCallback(() => setSplash(false), [])

  if (splash) return <SplashScreen onComplete={finishSplash} />
  if (!authed) {
    return (
      <Login
        onLogin={() => {
          try { window.sessionStorage.setItem(SESSION_KEY, '1') } catch { /* storage unavailable */ }
          setAuthed(true)
        }}
      />
    )
  }
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
