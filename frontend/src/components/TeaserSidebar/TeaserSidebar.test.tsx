import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { TeaserCombo } from '../../api/types'
import { TeaserSidebar } from './TeaserSidebar'

const combo: TeaserCombo = {
  team_count: 2,
  legs: [
    {
      game_id: 'kc-buf',
      team: 'KC',
      opponent: 'BUF',
      gameday: '2026-09-14',
      original_line: -8.5,
      teased_line: -2.5,
      confidence: 81.3,
    },
    {
      game_id: 'sf-lar',
      team: 'SF',
      opponent: 'LAR',
      gameday: '2026-09-14',
      original_line: -8.5,
      teased_line: -2.5,
      confidence: 81.3,
    },
  ],
  combined_probability: 0.6608,
  breakeven_probability: 0.5745,
  edge_pct: 8.63,
}

describe('TeaserSidebar', () => {
  it('shows an empty state when there are no combos', () => {
    render(<TeaserSidebar combos={[]} loading={false} error={null} />)
    expect(screen.getByText(/No \+EV teasers this week/)).toBeInTheDocument()
  })

  it('shows a loading state', () => {
    render(<TeaserSidebar combos={[]} loading={true} error={null} />)
    expect(screen.getByText(/Loading teasers/)).toBeInTheDocument()
  })

  it('shows an error state', () => {
    render(<TeaserSidebar combos={[]} loading={false} error="boom" />)
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('renders a combo with its legs and edge', () => {
    render(<TeaserSidebar combos={[combo]} loading={false} error={null} />)
    expect(screen.getByText('2-Team Teaser')).toBeInTheDocument()
    expect(screen.getByText(/\+8\.6% edge/)).toBeInTheDocument()
    expect(screen.getByText(/KC/)).toBeInTheDocument()
    expect(screen.getByText(/vs BUF/)).toBeInTheDocument()
  })
})
