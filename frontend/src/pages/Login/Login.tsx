import { FormEvent, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { brand } from '../../branding/config'
import { useAuth } from '../../context/AuthContext'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const body = new URLSearchParams({ username, password })
      const resp = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      })
      if (!resp.ok) {
        const data = (await resp.json().catch(() => null)) as { detail?: string } | null
        setError(data?.detail ?? 'Login failed')
        return
      }
      const data = (await resp.json()) as { access_token: string }
      login(data.access_token, username)
      navigate(from, { replace: true })
    } catch {
      setError('Network error — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-app-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="font-display text-4xl text-app-green tracking-widest leading-none mb-1">
            {brand.appName.split(' ').map((w) => w[0]).join('')}
          </div>
          <div className="font-mono text-xs text-app-muted tracking-widest uppercase">
            {brand.appTagline}
          </div>
        </div>

        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="bg-app-bg2 border border-app-border rounded-lg p-6 space-y-4"
        >
          <h1 className="text-white font-semibold text-lg">Sign in</h1>

          {error && (
            <div className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded px-3 py-2">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <label className="text-app-muted text-xs font-semibold uppercase tracking-wider">
              Username
            </label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="w-full bg-app-bg border border-app-border rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-app-green"
            />
          </div>

          <div className="space-y-1">
            <label className="text-app-muted text-xs font-semibold uppercase tracking-wider">
              Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-app-bg border border-app-border rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-app-green"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-app-green text-app-bg font-semibold py-2 rounded text-sm tracking-wider uppercase hover:bg-app-green/90 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
