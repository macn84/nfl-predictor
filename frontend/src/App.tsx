import { useEffect, useState } from 'react'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { pageview } from './analytics'
import { brand } from './branding/config'
import { JobsModal } from './components/JobsModal/JobsModal'
import { ProtectedRoute } from './components/ProtectedRoute/ProtectedRoute'
import { AuthProvider, useAuth } from './context/AuthContext'
import { GameDetail } from './pages/GameDetail/GameDetail'
import { Login } from './pages/Login/Login'
import { SeasonTracker } from './pages/SeasonTracker/SeasonTracker'
import { WeeklyDashboard } from './pages/WeeklyDashboard/WeeklyDashboard'

function RouteTracker() {
  const location = useLocation()
  useEffect(() => {
    pageview(location.pathname + location.search)
  }, [location])
  return null
}

function NavBar() {
  const { isAuthenticated, username, logout } = useAuth()
  // Controls the background-job status popup (logged-in only).
  const [jobsOpen, setJobsOpen] = useState(false)
  // Controls the collapsed mobile menu (hidden at md: and above).
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <nav className="bg-app-bg2 border-b-2 border-app-green px-4 sm:px-6 flex flex-wrap items-stretch md:flex-nowrap">
      <div className="flex items-stretch w-full md:w-auto justify-between">
        <Link to={brand.logoLink ?? '/'} className="flex items-center gap-3 py-3 md:mr-8 shrink-0">
          {brand.navLogo ? (
            <img src={brand.navLogo.src} alt={brand.navLogo.alt} className="h-8 sm:h-10 w-auto" />
          ) : (
            <>
              <span className="font-display text-3xl sm:text-4xl text-app-green tracking-widest leading-none">
                {brand.appName.split(' ').map((w) => w[0]).join('')}
              </span>
              <div>
                <div className="font-display text-lg sm:text-xl text-white tracking-wider leading-none">
                  {brand.appName.toUpperCase()}
                </div>
                <div className="font-mono text-xs text-app-green tracking-widest">
                  {brand.appTagline.toUpperCase()}
                </div>
              </div>
            </>
          )}
        </Link>
        <button
          onClick={() => setMenuOpen((open) => !open)}
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
          className="md:hidden flex items-center text-app-muted hover:text-app-green px-2 self-center"
        >
          <span className="text-xs font-semibold uppercase tracking-wider border border-app-border rounded px-3 py-1">
            {menuOpen ? 'Close' : 'Menu'}
          </span>
        </button>
      </div>
      <div
        className={`${menuOpen ? 'flex' : 'hidden'} flex-col w-full md:flex md:flex-row md:items-stretch md:gap-1 md:flex-1`}
      >
        <Link
          to="/"
          onClick={() => setMenuOpen(false)}
          className="flex items-center text-app-muted hover:text-app-green text-xs font-semibold px-4 py-3 md:py-0 border-b-2 border-transparent hover:border-app-green transition-colors uppercase tracking-wider"
        >
          Weekly Picks
        </Link>
        <Link
          to="/season"
          onClick={() => setMenuOpen(false)}
          className="flex items-center text-app-muted hover:text-app-green text-xs font-semibold px-4 py-3 md:py-0 border-b-2 border-transparent hover:border-app-green transition-colors uppercase tracking-wider"
        >
          Season Tracker
        </Link>
      </div>
      <div
        className={`${menuOpen ? 'flex' : 'hidden'} flex-col items-start gap-3 w-full pb-3 md:pb-0 md:flex md:flex-row md:items-center md:w-auto md:ml-auto`}
      >
        {isAuthenticated ? (
          <>
            <span className="text-app-muted text-xs font-mono px-1 md:px-0">{username}</span>
            <button
              onClick={() => setJobsOpen(true)}
              className="text-app-muted hover:text-app-green text-xs font-semibold px-3 py-1 border border-app-border hover:border-app-green rounded transition-colors uppercase tracking-wider"
            >
              Jobs
            </button>
            <button
              onClick={logout}
              className="text-app-muted hover:text-app-green text-xs font-semibold px-3 py-1 border border-app-border hover:border-app-green rounded transition-colors uppercase tracking-wider"
            >
              Logout
            </button>
            <JobsModal open={jobsOpen} onClose={() => setJobsOpen(false)} />
          </>
        ) : (
          <Link
            to="/login"
            onClick={() => setMenuOpen(false)}
            className="text-app-muted hover:text-app-green text-xs font-semibold px-3 py-1 border border-app-border hover:border-app-green rounded transition-colors uppercase tracking-wider"
          >
            Login
          </Link>
        )}
      </div>
    </nav>
  )
}

function AppRoutes() {
  return (
    <div className="min-h-screen bg-app-bg text-app-text">
      <RouteTracker />
      <NavBar />
      <main className="px-4 sm:px-6 py-4 sm:py-6 max-w-7xl mx-auto">
        <Routes>
          <Route path="/" element={<WeeklyDashboard />} />
          <Route path="/season" element={<SeasonTracker />} />
          <Route path="/login" element={<Login />} />
          <Route
            path="/game/:week/:gameId"
            element={
              <ProtectedRoute>
                <GameDetail />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
    </div>
  )
}

export function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
