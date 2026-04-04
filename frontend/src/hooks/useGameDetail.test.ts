import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { fixtureGame } from '../test/fixtures'
import { useGameDetail } from './useGameDetail'

vi.mock('../api/predictions')

import * as api from '../api/predictions'

describe('useGameDetail', () => {
  it('returns data on success', async () => {
    vi.mocked(api.fetchGamePrediction).mockResolvedValueOnce(fixtureGame)
    const { result } = renderHook(() => useGameDetail(2024, 1, 'kc-buf'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toEqual(fixtureGame)
    expect(result.current.error).toBeNull()
  })

  it('returns error on failure', async () => {
    vi.mocked(api.fetchGamePrediction).mockRejectedValueOnce(new Error('Not found'))
    const { result } = renderHook(() => useGameDetail(2024, 1, 'ne-dal'))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toBeNull()
    expect(result.current.error).toBe('Not found')
  })
})
