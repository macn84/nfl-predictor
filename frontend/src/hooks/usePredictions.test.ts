import { renderHook, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { fixtureWeekPredictions } from '../test/fixtures'
import { usePredictions } from './usePredictions'

vi.mock('../api/predictions')

import * as api from '../api/predictions'

describe('usePredictions', () => {
  it('returns data on success', async () => {
    vi.mocked(api.fetchWeekPredictions).mockResolvedValueOnce(fixtureWeekPredictions)
    const { result } = renderHook(() => usePredictions(2024, 1))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toEqual(fixtureWeekPredictions)
    expect(result.current.error).toBeNull()
  })

  it('returns error on failure', async () => {
    vi.mocked(api.fetchWeekPredictions).mockRejectedValueOnce(new Error('404'))
    const { result } = renderHook(() => usePredictions(2024, 1))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toBeNull()
    expect(result.current.error).toBe('404')
  })
})
