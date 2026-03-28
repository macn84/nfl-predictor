import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { SortFilterBar } from './SortFilterBar'

describe('SortFilterBar', () => {
  it('renders sort options', () => {
    render(<SortFilterBar sortBy="confidence" onSortChange={() => {}} />)
    expect(screen.getByText('Confidence')).toBeInTheDocument()
    expect(screen.getByText('Game Day')).toBeInTheDocument()
  })

  it('highlights active sort option', () => {
    render(<SortFilterBar sortBy="gameday" onSortChange={() => {}} />)
    expect(screen.getByText('Game Day')).toHaveClass('bg-gray-700')
    expect(screen.getByText('Confidence')).not.toHaveClass('bg-gray-700')
  })

  it('calls onSortChange with correct value', async () => {
    const onSortChange = vi.fn()
    render(<SortFilterBar sortBy="confidence" onSortChange={onSortChange} />)
    await userEvent.click(screen.getByText('Game Day'))
    expect(onSortChange).toHaveBeenCalledWith('gameday')
  })
})
