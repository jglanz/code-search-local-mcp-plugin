/** Cache tags of the service API; invalidating a tag refetches every query that provides it. */
export enum CodeSearchApiTag {
  stats = "stats",
  paths = "paths",
  health = "health"
}
