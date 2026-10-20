import type { SxProps, Theme } from "@mui/material/styles"

import type { PathStat } from "@code-search-local/code-search-local-api"

import {
  formatCount,
  formatRatio,
  formatScore,
  formatTimestamp,
  NoValue
} from "../stats/formatUtils.js"
import { PathSortKey } from "./PathSortKey.js"

/** One column of a per-path analytics table. */
export interface PathColumn {
  /** The column id, also its sort key. */
  key: PathSortKey

  /** The heading. */
  label: string

  /** Right-aligned figures. */
  numeric: boolean

  /**
   * The cell text of a row.
   *
   * @param row the path row.
   * @returns the formatted value.
   */
  format(row: PathStat): string
}

/** The columns of the per-path tables (top paths, indexed paths), in cell order. */
export namespace PathColumns {
  /**
   * The cell layout of a column: figures and times never wrap; a path wraps only where it must.
   *
   * @param column the column.
   * @returns the cell's `sx`.
   */
  export function cellSxOf({ key }: PathColumn): SxProps<Theme> {
    return key === PathSortKey.path
      ? { overflowWrap: "anywhere" }
      : { whiteSpace: "nowrap" }
  }

  /** Every column. */
  export const All: readonly PathColumn[] = Object.freeze([
    {
      key: PathSortKey.path,
      label: "Path",
      numeric: false,
      format: ({ path }) => path
    },
    {
      key: PathSortKey.chunks,
      label: "Chunks",
      numeric: true,
      format: ({ chunks }) => formatCount(chunks)
    },
    {
      key: PathSortKey.appearances,
      label: "Appearances",
      numeric: true,
      format: ({ appearances }) => formatCount(appearances)
    },
    {
      key: PathSortKey.hits,
      label: "Hits",
      numeric: true,
      format: ({ hits }) => formatCount(hits)
    },
    {
      key: PathSortKey.misses,
      label: "Misses",
      numeric: true,
      format: ({ misses }) => formatCount(misses)
    },
    {
      key: PathSortKey.hitRatio,
      label: "Hit ratio",
      numeric: true,
      format: ({ appearances, hit_ratio }) =>
        appearances > 0 ? formatRatio(hit_ratio) : NoValue
    },
    {
      key: PathSortKey.topRanked,
      label: "Top-ranked",
      numeric: true,
      format: ({ top_ranked }) => formatCount(top_ranked)
    },
    {
      key: PathSortKey.bestScore,
      label: "Best score",
      numeric: true,
      format: ({ best_score }) => formatScore(best_score)
    },
    {
      key: PathSortKey.lastSeenAt,
      label: "Last seen",
      numeric: false,
      format: ({ last_seen_at }) => formatTimestamp(last_seen_at)
    }
  ])

  /**
   * The columns of the top-paths table: every column but the chunk count, which the service
   * reports only for indexed-path rows (`top_paths` rows omit it).
   */
  export const TopPaths: readonly PathColumn[] = Object.freeze(
    All.filter(({ key }) => key !== PathSortKey.chunks)
  )
}
