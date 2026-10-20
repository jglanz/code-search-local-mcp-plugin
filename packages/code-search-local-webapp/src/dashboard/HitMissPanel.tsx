import Box from "@mui/material/Box"
import Stack from "@mui/material/Stack"
import Typography from "@mui/material/Typography"

import { HitMiss, type HitMissSource } from "../stats/HitMiss.js"
import { HitMissMeter } from "./HitMissMeter.js"

/** Props of {@link HitMissPanel}. */
export interface HitMissPanelProps {
  /** The totals or one project's statistics. */
  source: HitMissSource

  /** The relevance threshold in effect. */
  threshold: number

  /** The panel heading. */
  title: string

  /** Whose measures these are (`totals`, `project`); prefixes every meter's test id. */
  scope: string
}

/**
 * The three hit/miss measures of one source side by side: relevance, non-empty results and
 * the query embedding cache.
 *
 * @param props the panel props.
 * @returns the panel.
 */
export function HitMissPanel({
  source,
  threshold,
  title,
  scope
}: HitMissPanelProps): React.ReactElement {
  return (
    <Stack component="section" spacing={1.5} aria-label={title}>
      <Typography variant="h6" component="h2">
        {title}
      </Typography>
      <Box
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: `repeat(auto-fit, minmax(${HitMissPanel.MinColumnWidthPx}px, 1fr))`
        }}
      >
        {HitMiss.allOf(source).map(hitMiss => (
          <HitMissMeter
            key={hitMiss.kind}
            hitMiss={hitMiss}
            threshold={threshold}
            scope={scope}
          />
        ))}
      </Box>
    </Stack>
  )
}

/** Companion constants for {@link HitMissPanel}. */
export namespace HitMissPanel {
  /** Narrowest meter column in px before the meters wrap onto a new row. */
  export const MinColumnWidthPx = 220
}
