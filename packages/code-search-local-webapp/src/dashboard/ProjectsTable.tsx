import Link from "@mui/material/Link"
import Stack from "@mui/material/Stack"
import Table from "@mui/material/Table"
import TableBody from "@mui/material/TableBody"
import TableCell from "@mui/material/TableCell"
import TableContainer from "@mui/material/TableContainer"
import TableHead from "@mui/material/TableHead"
import TableRow from "@mui/material/TableRow"
import Typography from "@mui/material/Typography"
import { Link as RouterLink, useNavigate } from "react-router"

import type { StatsSnapshot } from "@code-search-local/code-search-local-api"

import { AppRoutePaths } from "../routes/AppRoutePaths.js"
import { formatCount, formatTimestamp } from "../stats/formatUtils.js"
import { HitMiss } from "../stats/HitMiss.js"
import { countActiveJobs, listProjects } from "../stats/snapshotUtils.js"
import { ViewState } from "./ViewState.js"
import { ViewStateKind } from "./ViewStateKind.js"

/** Props of {@link ProjectsTable}. */
export interface ProjectsTableProps {
  /** The statistics snapshot whose projects are listed. */
  snapshot: StatsSnapshot
}

/**
 * Every registered project with its index size, last index time, searches, the three hit rates
 * and its active jobs. A row (or its root, a link for keyboard users) opens the project page.
 *
 * @param props the table props.
 * @returns the table, or its empty state.
 */
export function ProjectsTable({
  snapshot
}: ProjectsTableProps): React.ReactElement {
  const navigate = useNavigate(),
    projects = listProjects(snapshot)
  return (
    <Stack component="section" spacing={1.5} aria-label={ProjectsTable.Title}>
      <Typography variant="h6" component="h2">
        {ProjectsTable.Title}
      </Typography>
      {projects.length === 0 ? (
        <ViewState
          kind={ViewStateKind.empty}
          scope={ProjectsTable.TestId}
          message={ProjectsTable.EmptyMessage}
        />
      ) : (
        <TableContainer>
          <Table size="small" data-testid={ProjectsTable.TestId}>
            <TableHead>
              <TableRow>
                {ProjectsTable.Columns.map(({ label, numeric }) => (
                  <TableCell key={label} align={numeric ? "right" : "left"}>
                    {label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {projects.map(project => {
                const target = AppRoutePaths.projectPath(project.project_id)
                return (
                  <TableRow
                    key={project.project_id}
                    hover
                    data-testid={ProjectsTable.rowTestIdOf(project.project_id)}
                    onClick={() => void navigate(target)}
                    sx={{ cursor: "pointer" }}
                  >
                    <TableCell sx={{ overflowWrap: "anywhere" }}>
                      <Link
                        component={RouterLink}
                        to={target}
                        // The row navigates too; one history entry per click.
                        onClick={event => event.stopPropagation()}
                      >
                        {project.project_path}
                      </Link>
                    </TableCell>
                    <TableCell align="right">
                      {formatCount(project.files)}
                    </TableCell>
                    <TableCell align="right">
                      {formatCount(project.chunks)}
                    </TableCell>
                    <TableCell>{formatTimestamp(project.indexed_at)}</TableCell>
                    <TableCell align="right">
                      {formatCount(project.searches)}
                    </TableCell>
                    {HitMiss.allOf(project).map(hitMiss => (
                      <TableCell key={hitMiss.kind} align="right">
                        {HitMiss.formatRate(hitMiss)}
                      </TableCell>
                    ))}
                    <TableCell align="right">
                      {formatCount(
                        countActiveJobs(snapshot, project.project_path)
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  )
}

/** One column heading of {@link ProjectsTable}. */
export interface ProjectsColumn {
  /** The heading. */
  label: string

  /** Right-aligned figures. */
  numeric: boolean
}

/** Companion constants and helpers for {@link ProjectsTable}. */
export namespace ProjectsTable {
  /** The section heading. */
  export const Title = "Projects"

  /** Test id of the table (and the prefix of its rows and empty state). */
  export const TestId = "projects"

  /** Shown when no project is registered. */
  export const EmptyMessage =
    "No project is registered yet. Index a workspace (index_directory) to see it here."

  /** The column headings, in cell order. */
  export const Columns: readonly ProjectsColumn[] = Object.freeze([
    { label: "Project", numeric: false },
    { label: "Files", numeric: true },
    { label: "Chunks", numeric: true },
    { label: "Last indexed", numeric: false },
    { label: "Searches", numeric: true },
    ...HitMiss.Kinds.map(kind => ({
      label: HitMiss.labelOf(kind),
      numeric: true
    })),
    { label: "Active jobs", numeric: true }
  ])

  /**
   * The test id of one project's row.
   *
   * @param projectId the project id.
   * @returns `projects-row-<projectId>`.
   */
  export function rowTestIdOf(projectId: string): string {
    return `${TestId}-row-${projectId}`
  }
}
