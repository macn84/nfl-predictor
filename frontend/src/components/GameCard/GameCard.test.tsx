import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../../context/AuthContext'
import { fixtureGame } from '../../test/fixtures'
import { GameCard } from './GameCard'

function renderCard() {
  return render(
    <AuthProvider>
      <MemoryRouter>
        <GameCard game={fixtureGame} mode="predictions" season={2024} />
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('GameCard', () => {
  it('renders the matchup', () => {
    renderCard()
    expect(screen.getByText(/BUF/)).toBeInTheDocument()
    expect(screen.getAllByText(/KC/).length).toBeGreaterThan(0)
  })

  it('renders the predicted winner', () => {
    renderCard()
    expect(screen.getByText('KC', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders the confidence badge', () => {
    renderCard()
    expect(screen.getByText('71.4%')).toBeInTheDocument()
  })

  it('does not link to game detail when unauthenticated', () => {
    renderCard()
    // No token in localStorage → unauthenticated → card is a div, not a link
    expect(screen.queryByRole('link')).toBeNull()
  })
})
