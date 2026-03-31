import { Link, Route, Routes } from 'react-router-dom'
import smHeader from './assets/sm-header.png'
import { GameDetail } from './pages/GameDetail/GameDetail'
import { SeasonTracker } from './pages/SeasonTracker/SeasonTracker'
import { WeeklyDashboard } from './pages/WeeklyDashboard/WeeklyDashboard'

export function App() {
  return (
    <div className="min-h-screen bg-rtc-bg text-rtc-text">
      <nav className="bg-rtc-bg2 border-b-2 border-rtc-green px-6 flex items-stretch">
        <Link to="/" className="flex items-center py-2 mr-8 shrink-0">
          <img src={smHeader} alt="Roughing the Gambler — Sharp Picks. Smart Money." className="h-10 w-auto" />
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
