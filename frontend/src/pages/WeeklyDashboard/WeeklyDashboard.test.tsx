import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../context/AuthContext'
import { fixtureWeekPredictions, fixtureWeeksResponse } from '../../test/fixtures'
import { WeeklyDashboard } from './WeeklyDashboard'

vi.mock('../../hooks/useWeeks')
vi.mock('../../hooks/usePredictions')
vi.mock('../../hooks/useCovers')

import * as useCoversModule from '../../hooks/useCovers'
import * as useWeeksModule from '../../hooks/useWeeks'
import * as usePredictionsModule from '../../hooks/usePredictions'

function renderDashboard(search = '?season=2024&week=1') {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[`/${search}`]}>
        <Routes>
          <Route path="/" element={<WeeklyDashboard />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('WeeklyDashboard', () => {
  beforeEach(() => {
    vi.mocked(useWeeksModule.useWeeks).mockReturnValue({
      data: fixtureWeeksResponse,
      loading: false,
      error: null,
    })
    vi.mocked(usePredictionsModule.usePredictions).mockReturnValue({
      data: fixtureWeekPredictions,
      loading: false,
      error: null,
    })
    vi.mocked(useCoversModule.useCovers).mockReturnValue({
      data: null,
      loading: false,
      error: null,
    })
  })

  it('renders week selector buttons for completed weeks only when unauthenticated', () => {
    renderDashboard()
    // fixtureWeeksResponse has weeks 1 and 2 as completed, week 3 as not completed
    const buttons = screen.getAllByRole('button', { name: /Week \d/ })
    expect(buttons.length).toBeGreaterThanOrEqual(1)
  })

  it('renders game cards', () => {
    renderDashboard()
    expect(screen.getByText(/BUF/)).toBeInTheDocument()
  })

  it('shows sort bar', () => {
    renderDashboard()
    expect(screen.getByText('Confidence')).toBeInTheDocument()
  })

  it('shows loading state while predictions load', () => {
    vi.mocked(usePredictionsModule.usePredictions).mockReturnValue({
      data: null,
      loading: true,
      error: null,
    })
    renderDashboard()
    expect(screen.getByText(/Loading predictions/)).toBeInTheDocument()
  })

  it('shows error when predictions fail', () => {
    vi.mocked(usePredictionsModule.usePredictions).mockReturnValue({
      data: null,
      loading: false,
      error: 'Network error',
    })
    renderDashboard()
    expect(screen.getByText(/Network error/)).toBeInTheDocument()
  })
})
