import { Link, Route, Routes } from 'react-router-dom'
import { GameDetail } from './pages/GameDetail/GameDetail'
import { SeasonTracker } from './pages/SeasonTracker/SeasonTracker'
import { WeeklyDashboard } from './pages/WeeklyDashboard/WeeklyDashboard'

export function App() {
  return (
    <div className="min-h-screen bg-rtc-bg text-rtc-text">
      <nav className="bg-rtc-bg2 border-b-2 border-rtc-green px-6 flex items-stretch">
        <Link to="/" className="flex items-center gap-3 py-3 mr-8 shrink-0">
          <span className="font-display text-4xl text-rtc-green tracking-widest leading-none">
            RTC
          </span>
          <div>
            <div className="font-display text-xl text-white tracking-wider leading-none">
              ROUGHING THE GAMBLER
            </div>
            <div className="font-mono text-xs text-rtc-green tracking-widest">
              SHARP PICKS. SMART MONEY.
            </div>
          </div>
        </Link>
        <div className="flex items-stretch gap-1">
          <Link
            to="/"
            className="flex items-center text-rtc-muted hover:text-rtc-green text-xs font-semibold px-4 border-b-2 border-transparent hover:border-rtc-green transition-colors uppercase tracking-wider"
          >
            Weekly Picks
          </Link>
          <Link
            to="/season"
            className="flex items-center text-rtc-muted hover:text-rtc-green text-xs font-semibold px-4 border-b-2 border-transparent hover:border-rtc-green transition-colors uppercase tracking-wider"
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
