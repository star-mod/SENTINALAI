import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import { useState } from 'react'
import App from './App'
import SplashScreen from './components/SplashScreen'
import Login from './components/Login'

function Root() {
  const [splash, setSplash] = useState(true)
  const [authed, setAuthed] = useState(false)
  if (splash) return <SplashScreen onComplete={() => setSplash(false)} />
  if (!authed) return <Login onLogin={() => setAuthed(true)} />
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
