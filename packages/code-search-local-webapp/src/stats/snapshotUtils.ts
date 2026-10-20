import { orderBy, sortBy } from "lodash-es"

import {
  zJobStatus,
  type Job,
  type JobStatus,
  type ProjectStats,
  type StatsSnapshot
} from "@code-search-local/code-search-local-api"

import { SortDirection } from "../util/SortDirection.js"

/** Job statuses that still need the indexer: the job is waiting or running. */
export const ActiveJobStatuses: readonly JobStatus[] = Object.freeze([
  zJobStatus.enum.queued,
  zJobStatus.enum.running
])

/**
 * Every registered project, ordered by root.
 *
 * @param snapshot the statistics snapshot.
 * @returns the projects.
 */
export function listProjects(snapshot: StatsSnapshot): ProjectStats[] {
  return sortBy(
    Object.values(snapshot.projects),
    ({ project_path }) => project_path
  )
}

/**
 * The project with an id (the SHA-256 digest of its root, as route parameters carry it).
 *
 * @param snapshot the statistics snapshot.
 * @param projectId the project id.
 * @returns the project, or undefined when no registered project has the id.
 */
export function findProjectById(
  snapshot: StatsSnapshot,
  projectId: string
): ProjectStats {
  return Object.values(snapshot.projects).find(
    ({ project_id }) => project_id === projectId
  )
}

/**
 * The jobs of one project, most recently queued first.
 *
 * @param snapshot the statistics snapshot.
 * @param projectPath the project root.
 * @returns the jobs.
 */
export function listProjectJobs(
  snapshot: StatsSnapshot,
  projectPath: string
): Job[] {
  return orderBy(
    Object.values(snapshot.jobs).filter(
      ({ project_path }) => project_path === projectPath
    ),
    ({ queued_at }) => Date.parse(queued_at),
    SortDirection.desc
  )
}

/**
 * Whether a job still needs the indexer.
 *
 * @param job the job.
 * @returns true while it is queued or running.
 */
export function isActiveJob({ status }: Job): boolean {
  return ActiveJobStatuses.includes(status)
}

/**
 * How many jobs of a project are queued or running.
 *
 * @param snapshot the statistics snapshot.
 * @param projectPath the project root.
 * @returns the count.
 */
export function countActiveJobs(
  snapshot: StatsSnapshot,
  projectPath: string
): number {
  return listProjectJobs(snapshot, projectPath).filter(isActiveJob).length
}

/**
 * The fraction of a job's changed files processed so far.
 *
 * @param job the job.
 * @returns 0..1, or undefined before the job knows how many files changed.
 */
export function jobProgressOf({ files_processed, files_total }: Job): number {
  return files_total == null || files_total === 0
    ? undefined
    : Math.min(files_processed / files_total, 1)
}
