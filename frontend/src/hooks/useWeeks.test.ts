import { renderHook, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { fixtureWeeksResponse } from '../test/fixtures'
import { useWeeks } from './useWeeks'

vi.mock('../api/predictions')

import * as api from '../api/predictions'

describe('useWeeks', () => {
  it('returns data on success', async () => {
    vi.mocked(api.fetchWeeks).mockResolvedValueOnce(fixtureWeeksResponse)
    const { result } = renderHook(() => useWeeks(2024))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toEqual(fixtureWeeksResponse)
    expect(result.current.error).toBeNull()
  })

  it('returns error on failure', async () => {
    vi.mocked(api.fetchWeeks).mockRejectedValueOnce(new Error('Network error'))
    const { result } = renderHook(() => useWeeks(2024))

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.data).toBeNull()
    expect(result.current.error).toBe('Network error')
  })

  it('starts in loading state', () => {
    vi.mocked(api.fetchWeeks).mockReturnValueOnce(new Promise(() => {}))
    const { result } = renderHook(() => useWeeks(2024))
    expect(result.current.loading).toBe(true)
  })
})
