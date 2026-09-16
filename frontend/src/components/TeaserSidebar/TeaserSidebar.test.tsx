import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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
  it('shows a "Load Teasers" button before anything is requested, and does not fetch', () => {
    render(<TeaserSidebar combos={[]} loading={false} error={null} requested={false} onRequest={() => {}} />)
    expect(screen.getByRole('button', { name: /Load Teasers/i })).toBeInTheDocument()
    expect(screen.queryByText(/No \+EV teasers this week/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Loading teasers/)).not.toBeInTheDocument()
  })

  it('calls onRequest when the Load Teasers button is clicked', () => {
    const onRequest = vi.fn()
    render(<TeaserSidebar combos={[]} loading={false} error={null} requested={false} onRequest={onRequest} />)
    fireEvent.click(screen.getByRole('button', { name: /Load Teasers/i }))
    expect(onRequest).toHaveBeenCalledTimes(1)
  })

  it('shows an empty state when requested and there are no combos', () => {
    render(<TeaserSidebar combos={[]} loading={false} error={null} requested={true} onRequest={() => {}} />)
    expect(screen.getByText(/No \+EV teasers this week/)).toBeInTheDocument()
  })

  it('shows a loading state once requested', () => {
    render(<TeaserSidebar combos={[]} loading={true} error={null} requested={true} onRequest={() => {}} />)
    expect(screen.getByText(/Loading teasers/)).toBeInTheDocument()
  })

  it('shows an error state once requested', () => {
    render(<TeaserSidebar combos={[]} loading={false} error="boom" requested={true} onRequest={() => {}} />)
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('renders a combo with its legs and edge once requested', () => {
    render(<TeaserSidebar combos={[combo]} loading={false} error={null} requested={true} onRequest={() => {}} />)
    expect(screen.getByText('2-Team Teaser')).toBeInTheDocument()
    expect(screen.getByText(/\+8\.6% edge/)).toBeInTheDocument()
    expect(screen.getByText(/KC/)).toBeInTheDocument()
    expect(screen.getByText(/vs BUF/)).toBeInTheDocument()
  })
})
