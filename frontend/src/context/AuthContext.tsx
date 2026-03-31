import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const TOKEN_KEY = 'nfl_auth_token'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  username: string | null
  login: (token: string, username: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [username, setUsername] = useState<string | null>(null)

  // Validate token on mount by calling /auth/me
  useEffect(() => {
    if (!token) return
    fetch('/api/v1/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error('invalid')
        return r.json() as Promise<{ username: string }>
      })
      .then((data) => setUsername(data.username))
      .catch(() => {
        // Token expired or invalid — clear it
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setUsername(null)
      })
  }, [token])

  const login = useCallback((newToken: string, newUsername: string) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
    setUsername(newUsername)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUsername(null)
  }, [])

  const value = useMemo(
    () => ({ token, isAuthenticated: token !== null, username, login, logout }),
    [token, username, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
