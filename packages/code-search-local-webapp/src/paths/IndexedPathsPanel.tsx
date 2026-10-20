import Alert from "@mui/material/Alert"
import Stack from "@mui/material/Stack"
import Typography from "@mui/material/Typography"

import { useProjectPaths } from "../api/dashboardQueries.js"
import { describeQueryError } from "../api/queryErrorUtils.js"
import { ViewState } from "../dashboard/ViewState.js"
import { ViewStateKind } from "../dashboard/ViewStateKind.js"
import { PathTable } from "./PathTable.js"
import { PathTreeView } from "./PathTreeView.js"

/** Props of {@link IndexedPathsPanel}. */
export interface IndexedPathsPanelProps {
  /** The project's absolute root. */
  projectPath: string
}

/**
 * Every file of the project's committed generation with its search analytics (`getPaths`,
 * refreshed while shown): a directory tree summing the analytics per directory above a sortable,
 * filterable file table (each full width: the table has nine columns).
 *
 * @param props the panel props.
 * @returns the panel.
 */
export function IndexedPathsPanel({
  projectPath
}: IndexedPathsPanelProps): React.ReactElement {
  const { data, error } = useProjectPaths(projectPath)
  return (
    <Stack
      component="section"
      spacing={1.5}
      aria-label={IndexedPathsPanel.Title}
    >
      <Typography variant="h6" component="h2">
        {IndexedPathsPanel.Title}
      </Typography>
      {data == null ? (
        error == null ? (
          <ViewState
            kind={ViewStateKind.loading}
            scope={IndexedPathsPanel.TestId}
            message={IndexedPathsPanel.LoadingMessage}
          />
        ) : (
          <ViewState
            kind={ViewStateKind.error}
            scope={IndexedPathsPanel.TestId}
            message={`${IndexedPathsPanel.ErrorMessage}: ${describeQueryError(error)}`}
          />
        )
      ) : data.generation == null || data.paths.length === 0 ? (
        <ViewState
          kind={ViewStateKind.empty}
          scope={IndexedPathsPanel.TestId}
          message={
            data.generation == null
              ? IndexedPathsPanel.NotIndexedMessage
              : IndexedPathsPanel.NoFilesMessage
          }
        />
      ) : (
        <Stack spacing={2} data-testid={IndexedPathsPanel.TestId}>
          {error == null ? null : (
            <Alert severity="warning">
              {`${IndexedPathsPanel.StaleMessage}: ${describeQueryError(error)}`}
            </Alert>
          )}
          <Typography variant="caption" color="text.secondary">
            {`${IndexedPathsPanel.GenerationLabel} ${data.generation}`}
          </Typography>
          <PathTreeView paths={data.paths} />
          <PathTable paths={data.paths} />
        </Stack>
      )}
    </Stack>
  )
}

/** Companion constants for {@link IndexedPathsPanel}. */
export namespace IndexedPathsPanel {
  /** The section heading. */
  export const Title = "Indexed paths"

  /** Test id of the loaded panel (and the prefix of its states). */
  export const TestId = "indexed-paths"

  /** Shown until the first response. */
  export const LoadingMessage = "Loading indexed paths…"

  /** Precedes the reason when the paths failed to load. */
  export const ErrorMessage = "Indexed paths failed to load"

  /** Precedes the reason when a refresh failed and the last paths are still shown. */
  export const StaleMessage =
    "Showing the last indexed paths; the refresh failed"

  /** Shown for a project without a committed generation. */
  export const NotIndexedMessage =
    "This project has no committed index yet; its paths appear after the first indexing job succeeds."

  /** Shown when the committed generation holds no file. */
  export const NoFilesMessage = "The committed index holds no files."

  /** Precedes the generation name. */
  export const GenerationLabel = "Generation"
}
