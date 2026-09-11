import type { GameCoverPrediction, GamePrediction } from '../api/types'

/**
 * One game's picks, flattened for external consumption (other systems / LLMs).
 * Field names are stable and intentionally redundant with the API types so
 * this shape can be handed off without also shipping `types.ts`.
 */
export interface PicksExportRow {
  game_id: string
  season: number
  week: number
  gameday: string
  home_team: string
  away_team: string
  /** Moneyline (heads-up) pick — team predicted to win outright. */
  moneyline_pick: string
  /** Team predicted to cover the spread. */
  spread_pick_team: string
  /**
   * The line `spread_pick_team` is covering, in sportsbook convention
   * (negative = favourite, positive = underdog), e.g. -3.5 or +3.5.
   */
  spread_pick_line: number
}

/**
 * Converts the cached home-relative spread (nflverse convention: positive =
 * home favoured) into the sportsbook-style line for a given team, flipping
 * sign only at this display/export boundary — never mutate the stored value.
 * Mirrors `formatSpread()` in `GameCard.tsx`; kept in sync with that logic.
 *
 * @param team - The team to express the line for.
 * @param homeTeam - The game's home team (spread is relative to this team).
 * @param spread - Cached spread: positive = home favoured, negative = away favoured.
 * @returns The line `team` is playing at, sportsbook convention.
 */
function lineForTeam(team: string, homeTeam: string, spread: number): number {
  const homeLine = -spread
  return team === homeTeam ? homeLine : -homeLine
}

/**
 * Joins moneyline predictions and cover predictions by `game_id` into flat
 * export rows. Games without a settled cover pick (no line yet, or the model
 * hasn't produced a `predicted_cover`) are omitted rather than emitted with
 * nulls, so every row in the output is a complete, usable pick.
 *
 * @param predictions - Moneyline predictions for the week (from `usePredictions`).
 * @param covers - Spread/cover predictions for the same week (from `useCovers`).
 * @returns One row per game that has both a moneyline pick and a settled cover pick.
 */
export function buildPicksExport(
  predictions: GamePrediction[],
  covers: GameCoverPrediction[],
): PicksExportRow[] {
  const coversById = new Map(covers.map((c) => [c.game_id, c]))
  const rows: PicksExportRow[] = []

  for (const prediction of predictions) {
    const cover = coversById.get(prediction.game_id)
    if (!cover || cover.spread === null || cover.predicted_cover === null) continue

    rows.push({
      game_id: prediction.game_id,
      season: prediction.season,
      week: prediction.week,
      gameday: prediction.gameday,
      home_team: prediction.home_team,
      away_team: prediction.away_team,
      moneyline_pick: prediction.predicted_winner,
      spread_pick_team: cover.predicted_cover,
      spread_pick_line: lineForTeam(cover.predicted_cover, cover.home_team, cover.spread),
    })
  }

  return rows
}

/**
 * Serializes picks rows to pretty-printed JSON and triggers a browser
 * download via a temporary anchor click — the standard Blob download pattern.
 *
 * @param rows - Export rows, typically from `buildPicksExport`.
 * @param season - Season, used only to name the downloaded file.
 * @param week - Week, used only to name the downloaded file.
 */
export function downloadPicksJson(rows: PicksExportRow[], season: number, week: number): void {
  const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `picks_${season}_wk${week}.json`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
