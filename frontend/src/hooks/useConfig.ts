import { useEffect, useState } from 'react'
import { fetchFrontendConfig } from '../api/predictions'
import type { FrontendConfig } from '../api/types'

const DEFAULT_CONFIG: FrontendConfig = {
  cover_edge_threshold: 50, // show all until server responds
}

export function useConfig(): FrontendConfig {
  const [config, setConfig] = useState<FrontendConfig>(DEFAULT_CONFIG)

  useEffect(() => {
    fetchFrontendConfig()
      .then(setConfig)
      .catch(() => {
        // silently fall back to default
      })
  }, [])

  return config
}
