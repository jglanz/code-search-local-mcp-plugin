import { match } from "ts-pattern"

import type {
  ProjectStats,
  SearchTotals
} from "@code-search-local/code-search-local-api"

import { formatRatio, NoValue } from "./formatUtils.js"
import { HitMissKind } from "./HitMissKind.js"

/** Hits and misses of one {@link HitMissKind}, with the ratio the service computed. */
export interface HitMiss {
  /** Which measure this is. */
  kind: HitMissKind

  /** Events that counted as hits. */
  hits: number

  /** Events that counted as misses. */
  misses: number

  /** Hits over hits plus misses (0 when both are 0). */
  ratio: number
}

/** Where hit/miss counters are read from: the totals, or one project's statistics. */
export type HitMissSource = SearchTotals | ProjectStats

/** The snapshot keys of one {@link HitMissKind}. */
export interface HitMissFields {
  /** Key of the hit counter. */
  hits: keyof SearchTotals

  /** Key of the miss counter. */
  misses: keyof SearchTotals

  /** Key of the ratio. */
  ratio: keyof SearchTotals
}

/** Companion constants and helpers for {@link HitMiss}. */
export namespace HitMiss {
  /** Every measure, in display order. */
  export const Kinds: readonly HitMissKind[] = Object.freeze([
    HitMissKind.relevance,
    HitMissKind.results,
    HitMissKind.queryCache
  ])

  /**
   * The snapshot keys of each measure (the same in `totals` and in each project). They must stay
   * the keys `openapi.yaml` documents; `keyof SearchTotals` makes tsc check them.
   */
  export const Fields: Readonly<Record<HitMissKind, HitMissFields>> =
    Object.freeze({
      [HitMissKind.relevance]: {
        hits: "search_relevance_hits",
        misses: "search_relevance_misses",
        ratio: "search_relevance_hit_ratio"
      },
      [HitMissKind.results]: {
        hits: "search_result_hits",
        misses: "search_result_misses",
        ratio: "search_result_hit_ratio"
      },
      [HitMissKind.queryCache]: {
        hits: "query_cache_hits",
        misses: "query_cache_misses",
        ratio: "query_cache_hit_ratio"
      }
    })

  /**
   * Read one measure. A counter a project has not recorded yet (state written before analytics
   * existed) counts as 0.
   *
   * @param source the totals or a project's statistics.
   * @param kind the measure.
   * @returns the hits, misses and ratio.
   */
  export function of(source: HitMissSource, kind: HitMissKind): HitMiss {
    const fields = Fields[kind],
      read = (key: keyof SearchTotals): number => {
        const value = source[key]
        return typeof value === "number" ? value : 0
      }
    return {
      kind,
      hits: read(fields.hits),
      misses: read(fields.misses),
      ratio: read(fields.ratio)
    }
  }

  /**
   * Every measure of a source, in {@link Kinds} order.
   *
   * @param source the totals or a project's statistics.
   * @returns one {@link HitMiss} per measure.
   */
  export function allOf(source: HitMissSource): HitMiss[] {
    return Kinds.map(kind => of(source, kind))
  }

  /**
   * How many events were counted.
   *
   * @param hitMiss the measure.
   * @returns hits plus misses.
   */
  export function totalOf({ hits, misses }: HitMiss): number {
    return hits + misses
  }

  /**
   * The hit rate as a percentage; no rate before the first event (0 of 0 is not 0%).
   *
   * @param hitMiss the measure.
   * @returns e.g. `66.7%`, or {@link NoValue}.
   */
  export function formatRate(hitMiss: HitMiss): string {
    return totalOf(hitMiss) > 0 ? formatRatio(hitMiss.ratio) : NoValue
  }

  /**
   * The measure's name, as its visualisation and table column are titled.
   *
   * @param kind the measure.
   * @returns e.g. `Relevance`.
   */
  export function labelOf(kind: HitMissKind): string {
    return match(kind)
      .with(HitMissKind.relevance, () => RelevanceLabel)
      .with(HitMissKind.results, () => ResultsLabel)
      .with(HitMissKind.queryCache, () => QueryCacheLabel)
      .exhaustive()
  }

  /**
   * What a hit means for the measure.
   *
   * @param kind the measure.
   * @param threshold the relevance threshold in effect (`shared.search_hit_min_score`).
   * @returns one sentence.
   */
  export function describe(kind: HitMissKind, threshold: number): string {
    return match(kind)
      .with(
        HitMissKind.relevance,
        () => `Searches whose top score reached the ${threshold} threshold`
      )
      .with(HitMissKind.results, () => ResultsDescription)
      .with(HitMissKind.queryCache, () => QueryCacheDescription)
      .exhaustive()
  }

  /** Title of the relevance measure. */
  export const RelevanceLabel = "Relevance"

  /** Title of the non-empty-results measure. */
  export const ResultsLabel = "Non-empty results"

  /** Title of the query-embedding-cache measure. */
  export const QueryCacheLabel = "Query cache"

  /** What a non-empty-results hit means. */
  export const ResultsDescription = "Searches that returned at least one result"

  /** What a query-cache hit means. */
  export const QueryCacheDescription =
    "Query embeddings served from the embedding cache"
}
