import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { fixtureWeeksResponse } from '../../test/fixtures'
import { WeekSelector } from './WeekSelector'

describe('WeekSelector', () => {
  it('renders a button for each week', () => {
    render(
      <WeekSelector weeks={fixtureWeeksResponse.weeks} selectedWeek={1} onSelect={() => {}} />,
    )
    expect(screen.getByText(/Week 1/)).toBeInTheDocument()
    expect(screen.getByText(/Week 2/)).toBeInTheDocument()
    expect(screen.getByText(/Week 3/)).toBeInTheDocument()
  })

  it('highlights the selected week', () => {
    render(
      <WeekSelector weeks={fixtureWeeksResponse.weeks} selectedWeek={2} onSelect={() => {}} />,
    )
    const week2Btn = screen.getByText(/Week 2/).closest('button')
    expect(week2Btn).toHaveClass('bg-blue-600')
  })

  it('calls onSelect with correct week number on click', async () => {
    const onSelect = vi.fn()
    render(
      <WeekSelector weeks={fixtureWeeksResponse.weeks} selectedWeek={1} onSelect={onSelect} />,
    )
    await userEvent.click(screen.getByText(/Week 3/))
    expect(onSelect).toHaveBeenCalledWith(3)
  })
})
