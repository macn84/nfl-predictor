import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../../context/AuthContext'
import { fixtureGame } from '../../test/fixtures'
import { GameCard, computeKelly } from './GameCard'
import { describe, it, expect } from 'vitest'

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

describe('computeKelly verdict adjustment', () => {
  const confidence = 71.4
  const juice = -145

  it('leaves the stake unchanged with no verdict (AGREE baseline)', () => {
    expect(computeKelly(confidence, juice)).toBeGreaterThan(0)
    expect(computeKelly(confidence, juice, 'AGREE')).toBe(computeKelly(confidence, juice))
  })

  it('does not change the stake for BOOST', () => {
    expect(computeKelly(confidence, juice, 'BOOST')).toBe(computeKelly(confidence, juice))
  })

  it('halves the stake for FADE', () => {
    const base = computeKelly(confidence, juice)
    const faded = computeKelly(confidence, juice, 'FADE')
    expect(faded).toBeCloseTo(base / 2, 2)
  })

  it('zeroes the stake for DISAGREE', () => {
    expect(computeKelly(confidence, juice, 'DISAGREE')).toBe(0)
  })
})
