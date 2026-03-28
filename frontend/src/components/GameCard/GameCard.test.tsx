import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { fixtureGame } from '../../test/fixtures'
import { GameCard } from './GameCard'

function renderCard() {
  return render(
    <MemoryRouter>
      <GameCard game={fixtureGame} season={2024} />
    </MemoryRouter>,
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

  it('links to the game detail page', () => {
    renderCard()
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/game/1/kc-buf?season=2024')
  })
})
