/**
 * Locale of every number, percentage and time the dashboard shows. Fixed (like the UI text) so
 * every user and every test sees the same separators; changing it changes every figure's format.
 */
export const DisplayLocale = "en-US"

/** Shown for a value that does not exist yet (no searches, never returned, never indexed). */
export const NoValue = "—"

/** Fraction digits of a percentage (`66.7%`). */
const RatioFractionDigits = 1

/** Fraction digits of a similarity score (`0.71`, `0.705`). */
const ScoreMinFractionDigits = 2

/** Most fraction digits of a similarity score. */
const ScoreMaxFractionDigits = 3

/** Fraction digits of a duration in seconds. */
const DurationFractionDigits = 1

const countFormat = new Intl.NumberFormat(DisplayLocale),
  ratioFormat = new Intl.NumberFormat(DisplayLocale, {
    style: "percent",
    minimumFractionDigits: RatioFractionDigits,
    maximumFractionDigits: RatioFractionDigits
  }),
  scoreFormat = new Intl.NumberFormat(DisplayLocale, {
    minimumFractionDigits: ScoreMinFractionDigits,
    maximumFractionDigits: ScoreMaxFractionDigits
  }),
  durationFormat = new Intl.NumberFormat(DisplayLocale, {
    minimumFractionDigits: DurationFractionDigits,
    maximumFractionDigits: DurationFractionDigits
  }),
  timestampFormat = new Intl.DateTimeFormat(DisplayLocale, {
    dateStyle: "medium",
    timeStyle: "medium"
  }),
  timeFormat = new Intl.DateTimeFormat(DisplayLocale, { timeStyle: "medium" })

/**
 * A count with thousands separators.
 *
 * @param count the count.
 * @returns e.g. `12,345`, or {@link NoValue} when absent.
 */
export function formatCount(count: number): string {
  return count == null ? NoValue : countFormat.format(count)
}

/**
 * A ratio as a percentage.
 *
 * @param ratio 0..1.
 * @returns e.g. `66.7%`, or {@link NoValue} when absent.
 */
export function formatRatio(ratio: number): string {
  return ratio == null ? NoValue : ratioFormat.format(ratio)
}

/**
 * A similarity score.
 *
 * @param score the cosine similarity.
 * @returns e.g. `0.71`, or {@link NoValue} when absent (never returned).
 */
export function formatScore(score: number): string {
  return score == null ? NoValue : scoreFormat.format(score)
}

/**
 * A duration.
 *
 * @param seconds the duration in seconds.
 * @returns e.g. `7.9 s`, or {@link NoValue} when absent.
 */
export function formatDuration(seconds: number): string {
  return seconds == null ? NoValue : `${durationFormat.format(seconds)} s`
}

/**
 * A service timestamp in the viewer's time zone.
 *
 * @param timestamp an ISO 8601 date-time with offset.
 * @returns the date and time, or {@link NoValue} when absent or unparseable.
 */
export function formatTimestamp(timestamp: string): string {
  const time = timestamp == null ? Number.NaN : Date.parse(timestamp)
  return Number.isNaN(time) ? NoValue : timestampFormat.format(time)
}

/**
 * A time of day (a refresh time).
 *
 * @param epochMs milliseconds since the epoch.
 * @returns the time, or {@link NoValue} when absent.
 */
export function formatTime(epochMs: number): string {
  return epochMs == null ? NoValue : timeFormat.format(epochMs)
}
