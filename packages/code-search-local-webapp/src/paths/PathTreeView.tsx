import FolderOutlined from "@mui/icons-material/FolderOutlined"
import InsertDriveFileOutlined from "@mui/icons-material/InsertDriveFileOutlined"
import Box from "@mui/material/Box"
import Button from "@mui/material/Button"
import Stack from "@mui/material/Stack"
import Typography from "@mui/material/Typography"
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView"
import { TreeItem } from "@mui/x-tree-view/TreeItem"
import { useState } from "react"

import type { PathStat } from "@code-search-local/code-search-local-api"

import { formatCount } from "../stats/formatUtils.js"
import { PathTree, type PathTreeNode } from "./PathTree.js"

/** Props of {@link PathTreeView}. */
export interface PathTreeViewProps {
  /** Every indexed file with its analytics. */
  paths: PathStat[]
}

/**
 * The indexed files as a directory tree. Every directory shows the appearances, hits and misses
 * summed over the files below it, so the parts of a project searches reach (and miss) stand out
 * before a single file is opened. Top-level directories start expanded; a click (or the arrow
 * keys) expands or collapses a directory.
 *
 * @param props the tree props.
 * @returns the tree.
 */
export function PathTreeView({ paths }: PathTreeViewProps): React.ReactElement {
  const nodes = PathTree.build(paths),
    [expandedItems, setExpandedItems] = useState<string[]>(() =>
      nodes.filter(({ isFile }) => !isFile).map(({ path }) => path)
    )
  return (
    <Stack spacing={1} data-testid={PathTreeView.TestId}>
      <Stack direction="row" spacing={1}>
        <Button
          size="small"
          onClick={() => setExpandedItems(PathTree.listDirectoryPaths(nodes))}
        >
          {PathTreeView.ExpandAllLabel}
        </Button>
        <Button size="small" onClick={() => setExpandedItems([])}>
          {PathTreeView.CollapseAllLabel}
        </Button>
      </Stack>
      <SimpleTreeView
        aria-label={PathTreeView.Label}
        expandedItems={expandedItems}
        onExpandedItemsChange={(_event, itemIds) => setExpandedItems(itemIds)}
      >
        {nodes.map(renderNode)}
      </SimpleTreeView>
    </Stack>
  )
}

/**
 * One tree item and, below it, its children.
 *
 * @param node the file or directory.
 * @returns the tree item.
 */
function renderNode(node: PathTreeNode): React.ReactElement {
  return (
    <TreeItem
      key={node.path}
      itemId={node.path}
      data-testid={PathTreeView.itemTestIdOf(node.path)}
      label={
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.25 }}>
          {node.isFile ? (
            <InsertDriveFileOutlined fontSize="small" aria-hidden />
          ) : (
            <FolderOutlined fontSize="small" aria-hidden />
          )}
          <Typography
            variant="body2"
            sx={{ flexGrow: 1, overflowWrap: "anywhere" }}
          >
            {node.name}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ whiteSpace: "nowrap" }}
          >
            {PathTreeView.summaryOf(node)}
          </Typography>
        </Box>
      }
    >
      {node.children.map(renderNode)}
    </TreeItem>
  )
}

/** Companion constants and helpers for {@link PathTreeView}. */
export namespace PathTreeView {
  /** Accessible name of the tree. */
  export const Label = "Indexed paths by directory"

  /** Test id of the tree section. */
  export const TestId = "path-tree"

  /** Label of the button that expands every directory. */
  export const ExpandAllLabel = "Expand all"

  /** Label of the button that collapses every directory. */
  export const CollapseAllLabel = "Collapse all"

  /** Label of a directory's file count. */
  export const FilesLabel = "Files"

  /** Label of a node's appearances. */
  export const AppearancesLabel = "Appearances"

  /** Label of a node's hits. */
  export const HitsLabel = "Hits"

  /** Label of a node's misses. */
  export const MissesLabel = "Misses"

  /** Between the figures of a node's summary. */
  export const SummarySeparator = " · "

  /**
   * The test id of one item.
   *
   * @param path the node's path.
   * @returns `path-tree-item-<path>`.
   */
  export function itemTestIdOf(path: string): string {
    return `${TestId}-item-${path}`
  }

  /**
   * The figures beside a node: its files (directories only), appearances, hits and misses.
   *
   * @param node the node.
   * @returns e.g. `Files 3 · Appearances 4 · Hits 2 · Misses 2`.
   */
  export function summaryOf({
    isFile,
    files,
    appearances,
    hits,
    misses
  }: PathTreeNode): string {
    return [
      ...(isFile ? [] : [`${FilesLabel} ${formatCount(files)}`]),
      `${AppearancesLabel} ${formatCount(appearances)}`,
      `${HitsLabel} ${formatCount(hits)}`,
      `${MissesLabel} ${formatCount(misses)}`
    ].join(SummarySeparator)
  }
}
