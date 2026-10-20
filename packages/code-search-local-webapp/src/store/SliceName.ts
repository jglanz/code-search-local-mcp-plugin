/**
 * Identity enum of every store slice: the value is both the slice `name` and its reducer key in
 * the root state. Renaming a value renames the key in preloaded state.
 */
export enum SliceName {
  codeSearchApi = "codeSearchApi",
  auth = "auth"
}
