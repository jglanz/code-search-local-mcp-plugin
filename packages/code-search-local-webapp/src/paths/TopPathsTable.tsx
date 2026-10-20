import Box from "@mui/material/Box"
import Stack from "@mui/material/Stack"
import Table from "@mui/material/Table"
import TableBody from "@mui/material/TableBody"
import TableCell from "@mui/material/TableCell"
import TableContainer from "@mui/material/TableContainer"
import TableHead from "@mui/material/TableHead"
import TableRow from "@mui/material/TableRow"
import Typography from "@mui/material/Typography"
import { maxBy } from "lodash-es"

import type { PathStat } from "@code-search-local/code-search-local-api"

import { ViewState } from "../dashboard/ViewState.js"
import { ViewStateKind } from "../dashboard/ViewStateKind.js"
import { PathColumns } from "./PathColumns.js"
import { PathSortKey } from "./PathSortKey.js"

/** Props of {@link TopPathsTable}. */
export interface TopPathsTableProps {
  /** The project's most frequently returned paths, highest appearances first. */
  paths: PathStat[]
}

/**
 * The files searches return most often, with a bar per row scaling its appearances against the
 * most frequent one (a single-hue magnitude bar; the count stays in text beside it).
 *
 * @param props the table props.
 * @returns the table, or its empty state.
 */
export function TopPathsTable({
  paths
}: TopPathsTableProps): React.ReactElement {
  const { appearances: most = 0 } = asRow(
    maxBy(paths, ({ appearances }) => appearances)
  )
  return (
    <Stack component="section" spacing={1.5} aria-label={TopPathsTable.Title}>
      <Typography variant="h6" component="h2">
        {TopPathsTable.Title}
      </Typography>
      {paths.length === 0 ? (
        <ViewState
          kind={ViewStateKind.empty}
          scope={TopPathsTable.TestId}
          message={TopPathsTable.EmptyMessage}
        />
      ) : (
        <TableContainer>
          <Table size="small" data-testid={TopPathsTable.TestId}>
            <TableHead>
              <TableRow>
                {PathColumns.TopPaths.map(({ key, label, numeric }) => (
                  <TableCell key={key} align={numeric ? "right" : "left"}>
                    {label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {paths.map(row => (
                <TableRow key={row.path}>
                  {PathColumns.TopPaths.map(column => (
                    <TableCell
                      key={column.key}
                      align={column.numeric ? "right" : "left"}
                      sx={PathColumns.cellSxOf(column)}
                    >
                      {column.format(row)}
                      {column.key === PathSortKey.appearances && most > 0 ? (
                        <Box
                          aria-hidden
                          data-testid={TopPathsTable.BarTestId}
                          sx={{
                            ml: "auto",
                            mt: 0.5,
                            height: TopPathsTable.BarHeightPx,
                            width: `${(row.appearances / most) * TopPathsTable.PercentScale}%`,
                            bgcolor: "chart.accent",
                            borderRadius: `0 ${TopPathsTable.DataEndRadiusPx}px ${TopPathsTable.DataEndRadiusPx}px 0`
                          }}
                        />
                      ) : null}
                    </TableCell>
                  ))}
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
 * A row, or an empty one when there is none (so destructuring defaults apply).
 *
 * @param row the row, possibly undefined.
 * @returns the row or `{}`.
 */
function asRow(row: PathStat): Partial<PathStat> {
  return row == null ? {} : row
}

/** Companion constants for {@link TopPathsTable}. */
export namespace TopPathsTable {
  /** The section heading. */
  export const Title = "Top paths"

  /** Test id of the table (and the prefix of its empty state). */
  export const TestId = "top-paths"

  /** Test id of each appearances bar. */
  export const BarTestId = "top-paths-bar"

  /** Shown before any search returned a file. */
  export const EmptyMessage =
    "No search has returned a file of this project yet."

  /** Height of an appearances bar in px. */
  export const BarHeightPx = 6

  /** Rounding of a bar's data end in px (the dataviz mark spec). */
  export const DataEndRadiusPx = 4

  /** Bar width scale: the share of the most frequent path, in percent. */
  export const PercentScale = 100
}
