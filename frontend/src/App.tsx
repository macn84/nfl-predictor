import { Link, Route, Routes } from 'react-router-dom'
import { GameDetail } from './pages/GameDetail/GameDetail'
import { SeasonTracker } from './pages/SeasonTracker/SeasonTracker'
import { WeeklyDashboard } from './pages/WeeklyDashboard/WeeklyDashboard'

export function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex gap-6 items-center">
        <span className="font-bold text-white">NFL Predictor</span>
        <Link to="/" className="text-gray-300 hover:text-white text-sm">
          Weekly Picks
        </Link>
        <Link to="/season" className="text-gray-300 hover:text-white text-sm">
          Season Tracker
        </Link>
      </nav>
      <main className="px-6 py-6">
        <Routes>
          <Route path="/" element={<WeeklyDashboard />} />
          <Route path="/game/:week/:gameId" element={<GameDetail />} />
          <Route path="/season" element={<SeasonTracker />} />
        </Routes>
      </main>
    </div>
  )
}
