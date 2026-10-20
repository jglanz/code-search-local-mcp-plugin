import Stack from "@mui/material/Stack"
import Table from "@mui/material/Table"
import TableBody from "@mui/material/TableBody"
import TableCell from "@mui/material/TableCell"
import TableContainer from "@mui/material/TableContainer"
import TableHead from "@mui/material/TableHead"
import TablePagination from "@mui/material/TablePagination"
import TableRow from "@mui/material/TableRow"
import TableSortLabel from "@mui/material/TableSortLabel"
import TextField from "@mui/material/TextField"
import Typography from "@mui/material/Typography"
import { useState } from "react"

import type { PathStat } from "@code-search-local/code-search-local-api"

import { ViewState } from "../dashboard/ViewState.js"
import { ViewStateKind } from "../dashboard/ViewStateKind.js"
import { formatCount } from "../stats/formatUtils.js"
import { SortDirection } from "../util/SortDirection.js"
import { PathColumns, type PathColumn } from "./PathColumns.js"
import { PathSortKey } from "./PathSortKey.js"
import { filterPathRows, sortPathRows } from "./pathTableUtils.js"

/** Props of {@link PathTable}. */
export interface PathTableProps {
  /** Every indexed file with its analytics. */
  paths: PathStat[]
}

/** How the table is ordered. */
export interface PathTableSort {
  /** The sorted column. */
  key: PathSortKey

  /** Its direction. */
  direction: SortDirection
}

/**
 * Every indexed file in a table that sorts by any column (a second click reverses the order),
 * filters by path text and pages through large projects.
 *
 * @param props the table props.
 * @returns the table.
 */
export function PathTable({ paths }: PathTableProps): React.ReactElement {
  const [sort, setSort] = useState<PathTableSort>(PathTable.DefaultSort),
    [filterText, setFilterText] = useState(""),
    [page, setPage] = useState(0),
    [rowsPerPage, setRowsPerPage] = useState(PathTable.DefaultRowsPerPage),
    matching = filterPathRows(paths, filterText),
    sorted = sortPathRows(matching, sort.key, sort.direction),
    shown = sorted.slice(page * rowsPerPage, (page + 1) * rowsPerPage),
    sortBy = (column: PathColumn) => {
      setSort(PathTable.nextSort(sort, column))
      setPage(0)
    }
  return (
    <Stack spacing={1.5} data-testid={PathTable.TestId}>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: "center", flexWrap: "wrap" }}
      >
        <TextField
          size="small"
          label={PathTable.FilterLabel}
          value={filterText}
          onChange={event => {
            setFilterText(event.target.value)
            setPage(0)
          }}
        />
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid={PathTable.CountTestId}
        >
          {`${formatCount(matching.length)} of ${formatCount(paths.length)} ${PathTable.FilesUnit}`}
        </Typography>
      </Stack>
      {matching.length === 0 ? (
        <ViewState
          kind={ViewStateKind.empty}
          scope={PathTable.TestId}
          message={`${PathTable.NoMatchMessage} "${filterText.trim()}"`}
        />
      ) : (
        <>
          <TableContainer>
            <Table size="small" aria-label={PathTable.Label}>
              <TableHead>
                <TableRow>
                  {PathColumns.All.map(column => (
                    <TableCell
                      key={column.key}
                      align={column.numeric ? "right" : "left"}
                      sortDirection={
                        sort.key === column.key ? sort.direction : false
                      }
                    >
                      <TableSortLabel
                        active={sort.key === column.key}
                        direction={
                          sort.key === column.key
                            ? sort.direction
                            : PathTable.defaultDirectionOf(column)
                        }
                        onClick={() => sortBy(column)}
                      >
                        {column.label}
                      </TableSortLabel>
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {shown.map(row => (
                  <TableRow key={row.path} data-testid={PathTable.RowTestId}>
                    {PathColumns.All.map(column => (
                      <TableCell
                        key={column.key}
                        align={column.numeric ? "right" : "left"}
                        sx={PathColumns.cellSxOf(column)}
                      >
                        {column.format(row)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={matching.length}
            page={page}
            rowsPerPage={rowsPerPage}
            rowsPerPageOptions={[...PathTable.RowsPerPageOptions]}
            onPageChange={(_event, next) => setPage(next)}
            onRowsPerPageChange={event => {
              setRowsPerPage(Number(event.target.value))
              setPage(0)
            }}
          />
        </>
      )}
    </Stack>
  )
}

/** Companion constants and helpers for {@link PathTable}. */
export namespace PathTable {
  /** Accessible name of the table. */
  export const Label = "Indexed files"

  /** Test id of the table section (and the prefix of its empty state). */
  export const TestId = "path-table"

  /** Test id of every body row. */
  export const RowTestId = "path-table-row"

  /** Test id of the "x of y files" line. */
  export const CountTestId = "path-table-count"

  /** Label of the filter field. */
  export const FilterLabel = "Filter paths"

  /** Unit after the file counts. */
  export const FilesUnit = "files"

  /** Shown, followed by the filter text, when no path matches. */
  export const NoMatchMessage = "No indexed path contains"

  /** The initial order: most frequently returned first. */
  export const DefaultSort: PathTableSort = {
    key: PathSortKey.appearances,
    direction: SortDirection.desc
  }

  /** Page sizes offered. */
  export const RowsPerPageOptions: readonly number[] = Object.freeze([
    25, 50, 100
  ])

  /** The initial page size. */
  export const DefaultRowsPerPage = RowsPerPageOptions[0]

  /**
   * The direction a column sorts in when first clicked: largest figures first, paths A–Z.
   *
   * @param column the column.
   * @returns the direction.
   */
  export function defaultDirectionOf(column: PathColumn): SortDirection {
    return column.numeric ? SortDirection.desc : SortDirection.asc
  }

  /**
   * The order after a click on a column heading: the same column reverses, another column
   * starts in its default direction.
   *
   * @param sort the current order.
   * @param column the clicked column.
   * @returns the next order.
   */
  export function nextSort(
    sort: PathTableSort,
    column: PathColumn
  ): PathTableSort {
    if (sort.key !== column.key)
      return { key: column.key, direction: defaultDirectionOf(column) }
    return {
      key: column.key,
      direction:
        sort.direction === SortDirection.asc
          ? SortDirection.desc
          : SortDirection.asc
    }
  }
}
