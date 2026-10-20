import Box from "@mui/material/Box"
import Typography from "@mui/material/Typography"

/** Props of {@link StatTile}. */
export interface StatTileProps {
  /** What the figure counts, in sentence case without a trailing colon. */
  label: string

  /** The formatted figure. */
  value: string

  /** Test id of the tile. */
  testId: string
}

/**
 * One headline figure: a label above a large value (the dataviz stat-tile contract; the number
 * is the chart).
 *
 * @param props the tile props.
 * @returns the tile.
 */
export function StatTile({
  label,
  value,
  testId
}: StatTileProps): React.ReactElement {
  return (
    <Box
      data-testid={testId}
      sx={{ p: 2, border: 1, borderColor: "divider", borderRadius: 1 }}
    >
      <Typography variant="body2" color="text.secondary" component="p">
        {label}
      </Typography>
      <Typography
        variant="h4"
        component="p"
        sx={{ fontWeight: StatTile.ValueFontWeight }}
      >
        {value}
      </Typography>
    </Box>
  )
}

/** Companion constants for {@link StatTile}. */
export namespace StatTile {
  /** Weight of the figure (semibold). */
  export const ValueFontWeight = 600
}
