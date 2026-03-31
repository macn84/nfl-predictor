import { Link, Route, Routes } from 'react-router-dom'
import { brand } from './branding/config'
import { GameDetail } from './pages/GameDetail/GameDetail'
import { SeasonTracker } from './pages/SeasonTracker/SeasonTracker'
import { WeeklyDashboard } from './pages/WeeklyDashboard/WeeklyDashboard'

export function App() {
  return (
    <div className="min-h-screen bg-app-bg text-app-text">
      <nav className="bg-app-bg2 border-b-2 border-app-green px-6 flex items-stretch">
        <Link to="/" className="flex items-center gap-3 py-3 mr-8 shrink-0">
          {brand.navLogo ? (
            <img src={brand.navLogo.src} alt={brand.navLogo.alt} className="h-10 w-auto" />
          ) : (
            <>
              <span className="font-display text-4xl text-app-green tracking-widest leading-none">
                {brand.appName.split(' ').map((w) => w[0]).join('')}
              </span>
              <div>
                <div className="font-display text-xl text-white tracking-wider leading-none">
                  {brand.appName.toUpperCase()}
                </div>
                <div className="font-mono text-xs text-app-green tracking-widest">
                  {brand.appTagline.toUpperCase()}
                </div>
              </div>
            </>
          )}
        </Link>
        <div className="flex items-stretch gap-1">
          <Link
            to="/"
            className="flex items-center text-app-muted hover:text-app-green text-xs font-semibold px-4 border-b-2 border-transparent hover:border-app-green transition-colors uppercase tracking-wider"
          >
            Weekly Picks
          </Link>
          <Link
            to="/season"
            className="flex items-center text-app-muted hover:text-app-green text-xs font-semibold px-4 border-b-2 border-transparent hover:border-app-green transition-colors uppercase tracking-wider"
          >
            Season Tracker
          </Link>
        </div>
      </nav>
      <main className="px-6 py-6 max-w-7xl mx-auto">
        <Routes>
          <Route path="/" element={<WeeklyDashboard />} />
          <Route path="/game/:week/:gameId" element={<GameDetail />} />
          <Route path="/season" element={<SeasonTracker />} />
        </Routes>
      </main>
    </div>
  )
}
