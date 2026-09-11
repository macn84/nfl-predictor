import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { fixtureCoverGame, fixtureGame } from '../test/fixtures'
import { useGameDetail } from './useGameDetail'

vi.mock('../api/predictions')

import * as api from '../api/predictions'

describe('useGameDetail', () => {
  it('returns data on success', async () => {
    vi.mocked(api.fetchGamePrediction).mockResolvedValueOnce(fixtureGame)
    const { result } = renderHook(() => useGameDetail(2024, 1, 'kc-buf', 'predictions'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toEqual(fixtureGame)
    expect(result.current.error).toBeNull()
  })

  it('returns error on failure', async () => {
    vi.mocked(api.fetchGamePrediction).mockRejectedValueOnce(new Error('Not found'))
    const { result } = renderHook(() => useGameDetail(2024, 1, 'ne-dal', 'predictions'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toBeNull()
    expect(result.current.error).toBe('Not found')
  })

  it('fetches cover data via fetchGameCoverPrediction when mode is covers', async () => {
    vi.mocked(api.fetchGameCoverPrediction).mockResolvedValueOnce(fixtureCoverGame)
    const { result } = renderHook(() => useGameDetail(2024, 1, 'kc-buf', 'covers'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toEqual(fixtureCoverGame)
    expect(api.fetchGameCoverPrediction).toHaveBeenCalledWith(2024, 1, 'kc-buf')
  })
})
