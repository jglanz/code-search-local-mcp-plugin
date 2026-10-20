import Box from "@mui/material/Box"

import type { SearchTotals } from "@code-search-local/code-search-local-api"

import { formatCount } from "../stats/formatUtils.js"
import { StatTile } from "./StatTile.js"

/** One headline figure of the totals row. */
export interface TotalsTile {
  /** The tile's label. */
  label: string

  /** The totals counter it shows. */
  field: keyof SearchTotals
}

/** Props of {@link TotalsCards}. */
export interface TotalsCardsProps {
  /** Totals over every registered project. */
  totals: SearchTotals
}

/**
 * The headline figures over every project: projects, files, chunks, searches and failed
 * searches.
 *
 * @param props the cards props.
 * @returns the row of tiles.
 */
export function TotalsCards({ totals }: TotalsCardsProps): React.ReactElement {
  return (
    <Box
      component="section"
      aria-label={TotalsCards.Label}
      data-testid={TotalsCards.TestId}
      sx={{
        display: "grid",
        gap: 2,
        gridTemplateColumns: `repeat(auto-fit, minmax(${TotalsCards.MinTileWidthPx}px, 1fr))`
      }}
    >
      {TotalsCards.Tiles.map(({ label, field }) => (
        <StatTile
          key={field}
          label={label}
          value={formatCount(totals[field] as number)}
          testId={TotalsCards.tileTestIdOf(field)}
        />
      ))}
    </Box>
  )
}

/** Companion constants and helpers for {@link TotalsCards}. */
export namespace TotalsCards {
  /** Accessible name of the row. */
  export const Label = "Totals"

  /** Test id of the row. */
  export const TestId = "totals"

  /** Narrowest tile in px before the tiles wrap. */
  export const MinTileWidthPx = 150

  /** The tiles, in display order. */
  export const Tiles: readonly TotalsTile[] = Object.freeze([
    { label: "Projects", field: "projects" },
    { label: "Indexed files", field: "files" },
    { label: "Chunks", field: "chunks" },
    { label: "Searches", field: "searches" },
    { label: "Failed searches", field: "search_failures" }
  ])

  /**
   * The test id of one tile.
   *
   * @param field the counter it shows.
   * @returns `totals-<field>`.
   */
  export function tileTestIdOf(field: keyof SearchTotals): string {
    return `${TestId}-${field}`
  }
}
