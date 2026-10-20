import Alert from "@mui/material/Alert"
import Stack from "@mui/material/Stack"

import type { StatsSnapshot } from "@code-search-local/code-search-local-api"

import {
  useDashboardHealth,
  useDashboardStats
} from "../api/dashboardQueries.js"
import { describeQueryError } from "../api/queryErrorUtils.js"
import { ServiceHeader } from "./ServiceHeader.js"
import { ViewState } from "./ViewState.js"
import { ViewStateKind } from "./ViewStateKind.js"

/** Props of {@link StatsView}. */
export interface StatsViewProps {
  /**
   * The page body for the latest snapshot.
   *
   * @param snapshot the statistics snapshot.
   * @returns the body.
   */
  children: (snapshot: StatsSnapshot) => React.ReactNode
}

/**
 * The frame of every dashboard page: polls the statistics snapshot and the service's health,
 * shows the service header above the page body, and the loading or error state until a first
 * snapshot arrives. A failed refresh keeps the last snapshot on screen (marked offline, with the
 * reason) instead of blanking the page.
 *
 * @param props the view props.
 * @returns the frame.
 */
export function StatsView({ children }: StatsViewProps): React.ReactElement {
  const stats = useDashboardStats(),
    health = useDashboardHealth(),
    { data: snapshot, error, fulfilledTimeStamp } = stats
  if (snapshot == null)
    return error == null ? (
      <ViewState
        kind={ViewStateKind.loading}
        scope={StatsView.TestId}
        message={StatsView.LoadingMessage}
      />
    ) : (
      <ViewState
        kind={ViewStateKind.error}
        scope={StatsView.TestId}
        message={`${StatsView.ErrorMessage}: ${describeQueryError(error)}`}
      />
    )
  return (
    <Stack spacing={3} data-testid={StatsView.TestId}>
      <ServiceHeader
        snapshot={snapshot}
        online={snapshot.online && error == null && health.error == null}
        refreshedAt={fulfilledTimeStamp}
      />
      {error == null ? null : (
        <Alert severity="warning" data-testid={StatsView.StaleTestId}>
          {`${StatsView.StaleMessage}: ${describeQueryError(error)}`}
        </Alert>
      )}
      {children(snapshot)}
    </Stack>
  )
}

/** Companion constants for {@link StatsView}. */
export namespace StatsView {
  /** Test id of the loaded frame (and the prefix of its states). */
  export const TestId = "stats-view"

  /** Test id of the stale-snapshot warning. */
  export const StaleTestId = "stats-view-stale"

  /** Shown until the first snapshot. */
  export const LoadingMessage = "Loading service statistics…"

  /** Precedes the reason when no snapshot could be loaded. */
  export const ErrorMessage = "Service statistics failed to load"

  /** Precedes the reason when a refresh failed and the last snapshot is shown. */
  export const StaleMessage = "Showing the last snapshot; the refresh failed"
}
