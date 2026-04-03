import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import { fixtureGame } from '../../test/fixtures'
import { GameDetail } from './GameDetail'

vi.mock('../../hooks/useGameDetail')

import * as useGameDetailModule from '../../hooks/useGameDetail'

function renderDetail(path = '/game/1/kc-buf?season=2024') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/game/:week/:gameId" element={<GameDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('GameDetail', () => {
  beforeEach(() => {
    vi.mocked(useGameDetailModule.useGameDetail).mockReturnValue({
      data: fixtureGame,
      loading: false,
      error: null,
    })
  })

  it('renders the matchup header', () => {
    renderDetail()
    expect(screen.getByText('BUF @ KC')).toBeInTheDocument()
  })

  it('renders the confidence badge', () => {
    renderDetail()
    expect(screen.getByText('71.4%')).toBeInTheDocument()
  })

  it('renders the predicted winner', () => {
    renderDetail()
    expect(screen.getByText('KC', { selector: 'span.font-bold' })).toBeInTheDocument()
  })

  it('renders factor bars for active factors', () => {
    renderDetail()
    expect(screen.getByText('Form')).toBeInTheDocument()
    expect(screen.getByText('Rest Advantage')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    vi.mocked(useGameDetailModule.useGameDetail).mockReturnValue({
      data: null,
      loading: true,
      error: null,
    })
    renderDetail()
    expect(screen.getByText(/Loading/)).toBeInTheDocument()
  })

  it('shows error state', () => {
    vi.mocked(useGameDetailModule.useGameDetail).mockReturnValue({
      data: null,
      loading: false,
      error: 'Not found',
    })
    renderDetail()
    expect(screen.getByText(/Not found/)).toBeInTheDocument()
  })

  it('has a back link to the week', () => {
    renderDetail()
    const backLink = screen.getByText(/← Week/)
    expect(backLink).toBeInTheDocument()
  })
})
