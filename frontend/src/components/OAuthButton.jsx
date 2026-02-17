import React, { useState, useEffect } from 'react'
import { LogIn, LogOut, User, Loader2, Copy, Check } from 'lucide-react'

const OAuthButton = () => {
  const [status, setStatus] = useState({ authenticated: false, email: null })
  const [loading, setLoading] = useState(false)
  const [authUrl, setAuthUrl] = useState(null)
  const [polling, setPolling] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => { checkStatus() }, [])

  useEffect(() => {
    if (!polling) return
    const interval = setInterval(async () => {
      const data = await checkStatus()
      if (data?.authenticated) {
        setPolling(false)
        setAuthUrl(null)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [polling])

  const checkStatus = async () => {
    try {
      const resp = await fetch('/auth/oauth/status')
      const data = await resp.json()
      setStatus(data)
      return data
    } catch { return null }
  }

  const handleLogin = async () => {
    setLoading(true)
    try {
      const resp = await fetch('/auth/oauth/start')
      const { auth_url } = await resp.json()
      setAuthUrl(auth_url)
      window.open(auth_url, '_blank', 'noopener')
      setPolling(true)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    await fetch('/auth/oauth/logout', { method: 'POST' })
    setStatus({ authenticated: false, email: null })
    setAuthUrl(null)
    setPolling(false)
  }

  const copyUrl = async () => {
    await navigator.clipboard.writeText(authUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (status.authenticated) {
    return (
      <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700 rounded-xl text-xs text-green-800 dark:text-green-300">
          <User className="w-3 h-3 shrink-0" />
          <span className="max-w-[140px] truncate">{status.email || 'ChatGPT Pro'}</span>
        </div>
        <button
          onClick={handleLogout}
          title="Sair"
          className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5">
      <button
        onClick={handleLogin}
        disabled={loading || polling}
        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium bg-black dark:bg-white text-white dark:text-black rounded-xl hover:opacity-80 disabled:opacity-50 transition-opacity whitespace-nowrap"
      >
        {(loading || polling)
          ? <Loader2 className="w-3 h-3 animate-spin" />
          : <LogIn className="w-3 h-3" />
        }
        {polling ? 'Aguardando login...' : 'Login ChatGPT'}
      </button>

      {authUrl && (
        <div className="text-xs text-gray-500 dark:text-gray-400 max-w-[220px]">
          <p className="mb-1 text-[10px]">Se o browser não abriu, copie o link:</p>
          <button
            onClick={copyUrl}
            className="flex items-center gap-1 w-full px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded-lg text-left font-mono text-[9px] break-all hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            {copied
              ? <><Check className="w-3 h-3 text-green-500 shrink-0" /> Copiado!</>
              : <><Copy className="w-3 h-3 shrink-0" /> {authUrl.substring(0, 55)}...</>
            }
          </button>
        </div>
      )}
    </div>
  )
}

export default OAuthButton
