import { orderBy } from "lodash-es"
import { match } from "ts-pattern"

import type { PathStat } from "@code-search-local/code-search-local-api"

import { SortDirection } from "../util/SortDirection.js"
import { PathSortKey } from "./PathSortKey.js"

/** Sort value of a missing score or time: sorts below every real value. */
const MissingSortValue = Number.NEGATIVE_INFINITY

/**
 * The value a row sorts by in a column.
 *
 * @param row the path row.
 * @param key the column.
 * @returns a number, or the path for the path column.
 */
export function sortValueOf(row: PathStat, key: PathSortKey): number | string {
  return match(key)
    .with(PathSortKey.path, () => row.path)
    .with(PathSortKey.chunks, () => (row.chunks == null ? 0 : row.chunks))
    .with(PathSortKey.appearances, () => row.appearances)
    .with(PathSortKey.hits, () => row.hits)
    .with(PathSortKey.misses, () => row.misses)
    .with(PathSortKey.hitRatio, () => row.hit_ratio)
    .with(PathSortKey.topRanked, () => row.top_ranked)
    .with(PathSortKey.bestScore, () =>
      row.best_score == null ? MissingSortValue : row.best_score
    )
    .with(PathSortKey.lastSeenAt, () =>
      row.last_seen_at == null ? MissingSortValue : Date.parse(row.last_seen_at)
    )
    .exhaustive()
}

/**
 * Sort rows by a column; ties keep path order.
 *
 * @param rows the rows.
 * @param key the column.
 * @param direction ascending or descending.
 * @returns a sorted copy.
 */
export function sortPathRows(
  rows: PathStat[],
  key: PathSortKey,
  direction: SortDirection
): PathStat[] {
  return orderBy(
    rows,
    [row => sortValueOf(row, key), ({ path }) => path],
    [direction, SortDirection.asc]
  )
}

/**
 * The rows whose path contains a text, ignoring case.
 *
 * @param rows the rows.
 * @param text the filter text; blank keeps every row.
 * @returns the matching rows, in their order.
 */
export function filterPathRows(rows: PathStat[], text: string): PathStat[] {
  const needle = text.trim().toLowerCase()
  return needle.length === 0
    ? rows
    : rows.filter(({ path }) => path.toLowerCase().includes(needle))
}
