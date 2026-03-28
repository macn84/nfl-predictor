import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import { fixtureWeekPredictions, fixtureWeeksResponse } from '../../test/fixtures'
import { WeeklyDashboard } from './WeeklyDashboard'

vi.mock('../../hooks/useWeeks')
vi.mock('../../hooks/usePredictions')

import * as useWeeksModule from '../../hooks/useWeeks'
import * as usePredictionsModule from '../../hooks/usePredictions'

function renderDashboard(search = '?season=2024&week=1') {
  return render(
    <MemoryRouter initialEntries={[`/${search}`]}>
      <Routes>
        <Route path="/" element={<WeeklyDashboard />} />
      </Routes>
    </MemoryRouter>,
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
  })

  it('renders week selector buttons', () => {
    renderDashboard()
    const buttons = screen.getAllByRole('button', { name: /Week \d/ })
    expect(buttons.length).toBeGreaterThanOrEqual(2)
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
