import Box from "@mui/material/Box"
import Typography from "@mui/material/Typography"

import { formatCount } from "../stats/formatUtils.js"
import { HitMiss } from "../stats/HitMiss.js"

/** Props of {@link HitMissMeter}. */
export interface HitMissMeterProps {
  /** The measure to show. */
  hitMiss: HitMiss

  /** The relevance threshold in effect, quoted in the relevance description. */
  threshold: number

  /** Whose measure this is (`totals`, `project`); prefixes the test id. */
  scope: string
}

/**
 * One hit/miss measure as a stat tile with a meter: the hit rate as the figure, a meter whose
 * fill is the hit share and whose track (a lighter step of the same hue) is the miss share, and
 * the hit and miss counts in text, so the rate never depends on colour. A measure with no events
 * yet shows no rate rather than a misleading 0%.
 *
 * @param props the meter props.
 * @returns the meter.
 */
export function HitMissMeter({
  hitMiss,
  threshold,
  scope
}: HitMissMeterProps): React.ReactElement {
  const { kind, hits, misses, ratio } = hitMiss,
    label = HitMiss.labelOf(kind),
    counted = HitMiss.totalOf(hitMiss) > 0,
    percent = counted ? ratio * HitMissMeter.PercentScale : 0,
    rate = HitMiss.formatRate(hitMiss)
  return (
    <Box
      data-testid={HitMissMeter.testIdOf(scope, kind)}
      sx={{
        p: 2,
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        display: "flex",
        flexDirection: "column",
        gap: 1
      }}
    >
      <Typography variant="subtitle2" component="h3">
        {label}
      </Typography>
      <Typography
        variant="h4"
        component="p"
        data-testid={HitMissMeter.RateTestId}
      >
        {rate}
      </Typography>
      <Box
        role="meter"
        aria-label={`${label} ${HitMissMeter.MeterLabelSuffix}`}
        aria-valuemin={0}
        aria-valuemax={HitMissMeter.PercentScale}
        aria-valuenow={percent}
        aria-valuetext={
          counted
            ? `${rate} (${formatCount(hits)} of ${formatCount(hits + misses)})`
            : HitMissMeter.NoEventsText
        }
        sx={{
          height: HitMissMeter.TrackHeightPx,
          bgcolor: "chart.track",
          borderRadius: `${HitMissMeter.DataEndRadiusPx}px`,
          overflow: "hidden"
        }}
      >
        <Box
          sx={{
            width: `${percent}%`,
            height: "100%",
            bgcolor: "chart.accent",
            borderRadius: `${HitMissMeter.DataEndRadiusPx}px`
          }}
        />
      </Box>
      <Typography
        variant="body2"
        color="text.secondary"
        data-testid={HitMissMeter.CountsTestId}
      >
        {counted
          ? `${HitMissMeter.HitsLabel} ${formatCount(hits)} · ${HitMissMeter.MissesLabel} ${formatCount(misses)}`
          : HitMissMeter.NoEventsText}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {HitMiss.describe(kind, threshold)}
      </Typography>
    </Box>
  )
}

/** Companion constants and helpers for {@link HitMissMeter}. */
export namespace HitMissMeter {
  /** Meter maximum: the ratio scaled to percent. */
  export const PercentScale = 100

  /** Height of the meter track in px. */
  export const TrackHeightPx = 8

  /** Rounding of the meter's data end in px (the dataviz mark spec). */
  export const DataEndRadiusPx = 4

  /** Appended to the measure's name in the meter's accessible name. */
  export const MeterLabelSuffix = "hit rate"

  /** Label before the hit count. */
  export const HitsLabel = "Hits"

  /** Label before the miss count. */
  export const MissesLabel = "Misses"

  /** Shown instead of counts before the first event. */
  export const NoEventsText = "No searches counted yet"

  /** Test id of the rate figure (inside the meter's own test id). */
  export const RateTestId = "hit-miss-rate"

  /** Test id of the counts line. */
  export const CountsTestId = "hit-miss-counts"

  /** Prefix of every meter's test id. */
  export const TestIdPrefix = "hit-miss"

  /**
   * The test id of one meter.
   *
   * @param scope whose measure it is.
   * @param kind the measure.
   * @returns `hit-miss-<scope>-<kind>`.
   */
  export function testIdOf(scope: string, kind: string): string {
    return `${TestIdPrefix}-${scope}-${kind}`
  }
}
