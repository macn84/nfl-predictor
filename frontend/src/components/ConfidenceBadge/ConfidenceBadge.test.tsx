import { render, screen } from '@testing-library/react'
import { ConfidenceBadge } from './ConfidenceBadge'

describe('ConfidenceBadge', () => {
  it('renders the confidence value', () => {
    render(<ConfidenceBadge confidence={71.4} />)
    expect(screen.getByText('71.4%')).toBeInTheDocument()
  })

  it('applies green class for high confidence', () => {
    const { container } = render(<ConfidenceBadge confidence={75} />)
    expect(container.firstChild).toHaveClass('bg-green-600')
  })

  it('applies yellow class for medium confidence', () => {
    const { container } = render(<ConfidenceBadge confidence={60} />)
    expect(container.firstChild).toHaveClass('bg-yellow-500')
  })

  it('applies red class for low confidence', () => {
    const { container } = render(<ConfidenceBadge confidence={51} />)
    expect(container.firstChild).toHaveClass('bg-red-600')
  })
})
