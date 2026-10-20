import Alert from "@mui/material/Alert"
import Box from "@mui/material/Box"
import CircularProgress from "@mui/material/CircularProgress"
import Typography from "@mui/material/Typography"
import { match } from "ts-pattern"

import { ViewStateKind } from "./ViewStateKind.js"

/** Props of {@link ViewState}. */
export interface ViewStateProps {
  /** Loading, error or empty. */
  kind: ViewStateKind

  /** What is loading, what failed (with the reason) or why there is nothing to show. */
  message: string

  /** Distinguishes the state of one view from another's (`<scope>-<kind>` test id). */
  scope: string
}

/**
 * The loading, error or empty state of a view: a spinner with a status message, an error alert,
 * or a muted explanation. Every view renders one of these instead of an empty area.
 *
 * @param props the state props.
 * @returns the state.
 */
export function ViewState({
  kind,
  message,
  scope
}: ViewStateProps): React.ReactElement {
  const testId = ViewState.testIdOf(scope, kind)
  return match(kind)
    .with(ViewStateKind.loading, () => (
      <Box
        role="status"
        data-testid={testId}
        sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2 }}
      >
        <CircularProgress size={ViewState.SpinnerSizePx} aria-hidden />
        <Typography color="text.secondary">{message}</Typography>
      </Box>
    ))
    .with(ViewStateKind.error, () => (
      <Alert severity="error" data-testid={testId}>
        {message}
      </Alert>
    ))
    .with(ViewStateKind.empty, () => (
      <Typography color="text.secondary" data-testid={testId} sx={{ py: 2 }}>
        {message}
      </Typography>
    ))
    .exhaustive()
}

/** Companion constants and helpers for {@link ViewState}. */
export namespace ViewState {
  /** Diameter of the loading spinner in px. */
  export const SpinnerSizePx = 20

  /**
   * The test id of one view's state.
   *
   * @param scope the view.
   * @param kind the state.
   * @returns `<scope>-<kind>`.
   */
  export function testIdOf(scope: string, kind: ViewStateKind): string {
    return `${scope}-${kind}`
  }
}
