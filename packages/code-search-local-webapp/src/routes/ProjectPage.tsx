import Stack from "@mui/material/Stack"
import Typography from "@mui/material/Typography"
import { useEffect } from "react"
import { useParams } from "react-router"

import type { StatsSnapshot } from "@code-search-local/code-search-local-api"

import { useDashboardStats } from "../api/dashboardQueries.js"
import { AppTitle } from "../app/AppTitle.js"
import { HitMissPanel } from "../dashboard/HitMissPanel.js"
import { JobsPanel } from "../dashboard/JobsPanel.js"
import { StatsView } from "../dashboard/StatsView.js"
import { IndexedPathsPanel } from "../paths/IndexedPathsPanel.js"
import { TopPathsTable } from "../paths/TopPathsTable.js"
import { formatCount, formatTimestamp } from "../stats/formatUtils.js"
import { findProjectById, listProjectJobs } from "../stats/snapshotUtils.js"
import type { ProjectRouteParams } from "./AppRoutePaths.js"
import { NotFoundPage } from "./NotFoundPage.js"

/**
 * One project (`/projects/:projectId`): the service header, the project's three hit/miss
 * measures, its top paths, its indexing jobs and its indexed paths. An id no registered project
 * has shows the not-found message.
 *
 * @returns the page.
 */
export function ProjectPage(): React.ReactElement {
  const { projectId } = useParams<ProjectRouteParams>(),
    { data: snapshot } = useDashboardStats(),
    project =
      snapshot == null ? undefined : findProjectById(snapshot, projectId),
    title = project == null ? ProjectPage.Title : project.project_path
  useEffect(() => {
    document.title = AppTitle.of(title)
  }, [title])
  return (
    <Stack spacing={3} data-testid={ProjectPage.TestId}>
      <StatsView>{snapshot => renderProject(snapshot, projectId)}</StatsView>
    </Stack>
  )
}

/**
 * The body of the page for one snapshot.
 *
 * @param snapshot the statistics snapshot.
 * @param projectId the route's project id.
 * @returns the project's sections, or the not-found message.
 */
function renderProject(
  snapshot: StatsSnapshot,
  projectId: string
): React.ReactElement {
  const project = findProjectById(snapshot, projectId)
  if (project == null)
    return (
      <NotFoundPage
        message={`${ProjectPage.UnknownProjectMessage} ${projectId}`}
      />
    )
  return (
    <>
      <Typography variant="h5" component="h1" sx={{ overflowWrap: "anywhere" }}>
        {project.project_path}
      </Typography>
      <Typography
        color="text.secondary"
        data-testid={ProjectPage.SummaryTestId}
      >
        {[
          `${formatCount(project.files)} ${ProjectPage.FilesUnit}`,
          `${formatCount(project.chunks)} ${ProjectPage.ChunksUnit}`,
          `${formatCount(project.searches)} ${ProjectPage.SearchesUnit}`,
          `${ProjectPage.IndexedLabel} ${formatTimestamp(project.indexed_at)}`
        ].join(ProjectPage.SummarySeparator)}
      </Typography>
      <HitMissPanel
        title={ProjectPage.HitMissTitle}
        scope={ProjectPage.HitMissScope}
        source={project}
        threshold={snapshot.shared.search_hit_min_score}
      />
      <TopPathsTable paths={project.top_paths} />
      <JobsPanel jobs={listProjectJobs(snapshot, project.project_path)} />
      <IndexedPathsPanel projectPath={project.project_path} />
    </>
  )
}

/** Companion constants for {@link ProjectPage}. */
export namespace ProjectPage {
  /** Document title until the project is known. */
  export const Title = "Project"

  /** Test id of the page root. */
  export const TestId = "project-page"

  /** Test id of the one-line summary under the heading. */
  export const SummaryTestId = "project-summary"

  /** Precedes the id of a project that is not registered. */
  export const UnknownProjectMessage = "No registered project has the id"

  /** Heading of the project's hit/miss measures. */
  export const HitMissTitle = "Search quality"

  /** Test id scope of the project's hit/miss meters. */
  export const HitMissScope = "project"

  /** Unit after the file count. */
  export const FilesUnit = "files"

  /** Unit after the chunk count. */
  export const ChunksUnit = "chunks"

  /** Unit after the search count. */
  export const SearchesUnit = "searches"

  /** Precedes the last index time. */
  export const IndexedLabel = "indexed"

  /** Between the summary's parts. */
  export const SummarySeparator = " · "
}
