/** A sortable column of the indexed-paths table (the value is the column's id). */
export enum PathSortKey {
  path = "path",
  chunks = "chunks",
  appearances = "appearances",
  hits = "hits",
  misses = "misses",
  hitRatio = "hitRatio",
  topRanked = "topRanked",
  bestScore = "bestScore",
  lastSeenAt = "lastSeenAt"
}
