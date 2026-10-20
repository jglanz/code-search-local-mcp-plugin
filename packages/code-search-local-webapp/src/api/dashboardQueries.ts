import { skipToken } from "@reduxjs/toolkit/query/react"

import { CodeSearchApi, type GetStatsArgs } from "./CodeSearchApi.js"
import { DashboardPolling } from "./DashboardPolling.js"

/** The `getStats` argument of the unfiltered snapshot every dashboard view shares. */
export const AllProjectsArgs: GetStatsArgs = {}

/** Options of every dashboard query: refreshed every {@link DashboardPolling.IntervalMs}. */
export const DashboardQueryOptions = {
  pollingInterval: DashboardPolling.IntervalMs
}

/**
 * The unfiltered statistics snapshot, refreshed every {@link DashboardPolling.IntervalMs}. Every
 * view shares one cache entry and one poll.
 *
 * @returns the query state.
 */
export function useDashboardStats() {
  return CodeSearchApi.useGetStatsQuery(AllProjectsArgs, DashboardQueryOptions)
}

/**
 * The service's liveness, refreshed every {@link DashboardPolling.IntervalMs}.
 *
 * @returns the query state.
 */
export function useDashboardHealth() {
  return CodeSearchApi.useGetHealthQuery(undefined, DashboardQueryOptions)
}

/**
 * Per-path analytics of one project, refreshed every {@link DashboardPolling.IntervalMs}.
 *
 * @param projectPath the absolute project root; nothing is requested while it is undefined.
 * @returns the query state.
 */
export function useProjectPaths(projectPath: string) {
  return CodeSearchApi.useGetPathsQuery(
    projectPath == null ? skipToken : projectPath,
    DashboardQueryOptions
  )
}
