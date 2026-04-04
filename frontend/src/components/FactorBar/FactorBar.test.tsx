import { render, screen } from '@testing-library/react'
import type { FactorResult } from '../../api/types'
import { FactorBar } from './FactorBar'
import { describe, it, expect } from 'vitest'

const activeFactors: FactorResult[] = [
  { name: 'form', score: 40.0, weight: 0.333, contribution: 13.3, supporting_data: {} },
  { name: 'ats_form', score: -20.0, weight: 0.333, contribution: -6.7, supporting_data: {} },
]

const skippedFactor: FactorResult = {
  name: 'betting_lines',
  score: 0.0,
  weight: 0.0,
  contribution: 0.0,
  supporting_data: { skipped: true },
}

describe('FactorBar', () => {
  it('renders factor label', () => {
    render(<FactorBar factor={activeFactors[0]} />)
    expect(screen.getByText('Form')).toBeInTheDocument()
  })

  it('shows positive score with + prefix', () => {
    render(<FactorBar factor={activeFactors[0]} />)
    expect(screen.getByText('+40.0')).toBeInTheDocument()
  })

  it('shows negative score without + prefix', () => {
    render(<FactorBar factor={activeFactors[1]} />)
    expect(screen.getByText('-20.0')).toBeInTheDocument()
  })

  it('shows skipped when weight is 0', () => {
    render(<FactorBar factor={skippedFactor} />)
    expect(screen.getByText('skipped')).toBeInTheDocument()
  })

  it('renders fill bar for active factor', () => {
    render(<FactorBar factor={activeFactors[0]} />)
    expect(screen.getByTestId('factor-bar-fill')).toBeInTheDocument()
  })

  it('does not render fill bar for skipped factor', () => {
    render(<FactorBar factor={skippedFactor} />)
    expect(screen.queryByTestId('factor-bar-fill')).not.toBeInTheDocument()
  })
})
