/**
 * The three hit/miss measures of search quality the service counts, for the totals and for
 * each project. The value is also the suffix of each visualisation's test id.
 */
export enum HitMissKind {
  /** The top score met the relevance threshold (`search_relevance_*`). */
  relevance = "relevance",

  /** The search returned at least one result (`search_result_*`). */
  results = "results",

  /** The query embedding came from the cache (`query_cache_*`). */
  queryCache = "queryCache"
}
