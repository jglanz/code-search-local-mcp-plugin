/** Which non-content state a view is in; the value is also the state's test id suffix. */
export enum ViewStateKind {
  /** The first response has not arrived. */
  loading = "loading",

  /** The request failed and there is nothing to show. */
  error = "error",

  /** The response arrived and holds nothing to show. */
  empty = "empty"
}
