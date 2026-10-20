import Box from "@mui/material/Box"
import Chip, { type ChipProps } from "@mui/material/Chip"
import LinearProgress from "@mui/material/LinearProgress"
import Stack from "@mui/material/Stack"
import Table from "@mui/material/Table"
import TableBody from "@mui/material/TableBody"
import TableCell from "@mui/material/TableCell"
import TableContainer from "@mui/material/TableContainer"
import TableHead from "@mui/material/TableHead"
import TableRow from "@mui/material/TableRow"
import Typography from "@mui/material/Typography"

import type { Job, JobStatus } from "@code-search-local/code-search-local-api"

import {
  formatCount,
  formatDuration,
  formatTimestamp,
  NoValue
} from "../stats/formatUtils.js"
import { isActiveJob, jobProgressOf } from "../stats/snapshotUtils.js"
import { ViewState } from "./ViewState.js"
import { ViewStateKind } from "./ViewStateKind.js"

/** Props of {@link JobsPanel}. */
export interface JobsPanelProps {
  /** The project's jobs, most recent first. */
  jobs: Job[]
}

/**
 * A project's most recent indexing jobs: status, progress over the changed files
 * (`files_processed / files_total`), when each was queued, how long it ran and why it failed.
 *
 * @param props the panel props.
 * @returns the panel.
 */
export function JobsPanel({ jobs }: JobsPanelProps): React.ReactElement {
  const shown = jobs.slice(0, JobsPanel.MaxJobs)
  return (
    <Stack component="section" spacing={1.5} aria-label={JobsPanel.Title}>
      <Typography variant="h6" component="h2">
        {JobsPanel.Title}
      </Typography>
      {shown.length === 0 ? (
        <ViewState
          kind={ViewStateKind.empty}
          scope={JobsPanel.TestId}
          message={JobsPanel.EmptyMessage}
        />
      ) : (
        <TableContainer>
          <Table size="small" data-testid={JobsPanel.TestId}>
            <TableHead>
              <TableRow>
                {JobsPanel.Columns.map(label => (
                  <TableCell key={label}>{label}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {shown.map(job => (
                <TableRow
                  key={job.job_id}
                  data-testid={JobsPanel.rowTestIdOf(job.job_id)}
                >
                  <TableCell>
                    <Chip
                      size="small"
                      variant="outlined"
                      color={JobsPanel.StatusColors[job.status]}
                      label={job.status}
                    />
                  </TableCell>
                  <TableCell sx={{ minWidth: JobsPanel.ProgressMinWidthPx }}>
                    {renderJobProgress(job)}
                  </TableCell>
                  <TableCell>{formatTimestamp(job.queued_at)}</TableCell>
                  <TableCell>{formatDuration(job.duration_seconds)}</TableCell>
                  <TableCell sx={{ overflowWrap: "anywhere" }}>
                    {job.error == null ? NoValue : job.error}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  )
}

/**
 * A job's progress bar and `processed / total` text; an indeterminate bar while an active job
 * does not know its total yet, no bar for a finished job that never counted its files.
 *
 * @param job the job.
 * @returns the cell content.
 */
function renderJobProgress(job: Job): React.ReactElement {
  const progress = jobProgressOf(job),
    text =
      progress == null
        ? `${formatCount(job.files_processed)} ${JobsPanel.FilesUnit}`
        : `${formatCount(job.files_processed)} / ${formatCount(job.files_total)} ${JobsPanel.FilesUnit}`
  return (
    <Box>
      {progress == null && !isActiveJob(job) ? null : (
        <LinearProgress
          aria-label={`${JobsPanel.ProgressLabel} ${job.job_id}`}
          variant={progress == null ? "indeterminate" : "determinate"}
          value={
            progress == null ? undefined : progress * JobsPanel.PercentScale
          }
        />
      )}
      <Typography variant="caption" color="text.secondary">
        {text}
      </Typography>
    </Box>
  )
}

/** Companion constants and helpers for {@link JobsPanel}. */
export namespace JobsPanel {
  /** The section heading. */
  export const Title = "Indexing jobs"

  /** Test id of the table (and the prefix of its rows and empty state). */
  export const TestId = "jobs"

  /** Most jobs listed; older ones are left out. */
  export const MaxJobs = 10

  /** Shown when the project has no job. */
  export const EmptyMessage = "No indexing job has run for this project."

  /** The column headings, in cell order. */
  export const Columns: readonly string[] = Object.freeze([
    "Status",
    "Progress",
    "Queued",
    "Duration",
    "Error"
  ])

  /** Unit after the file counts. */
  export const FilesUnit = "files"

  /** Accessible name prefix of a progress bar (followed by the job id). */
  export const ProgressLabel = "Progress of job"

  /** Progress bar maximum: the fraction scaled to percent. */
  export const PercentScale = 100

  /** Narrowest progress column in px. */
  export const ProgressMinWidthPx = 160

  /** Chip colour of each status (status colours always come with the status text). */
  export const StatusColors: Readonly<Record<JobStatus, ChipProps["color"]>> =
    Object.freeze({
      queued: "default",
      running: "info",
      succeeded: "success",
      failed: "error",
      cancelled: "warning",
      interrupted: "warning"
    })

  /**
   * The test id of one job's row.
   *
   * @param jobId the job id.
   * @returns `jobs-row-<jobId>`.
   */
  export function rowTestIdOf(jobId: string): string {
    return `${TestId}-row-${jobId}`
  }
}
