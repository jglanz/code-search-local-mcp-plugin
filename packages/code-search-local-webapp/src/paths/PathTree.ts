import { groupBy, sortBy, sumBy } from "lodash-es"

import type { PathStat } from "@code-search-local/code-search-local-api"

/** One file or directory of the indexed-paths tree, with analytics summed over its files. */
export interface PathTreeNode {
  /** Project-relative path; unique in the tree, so it is the tree item id. */
  path: string

  /** The last path segment. */
  name: string

  /** True for a file (a leaf), false for a directory. */
  isFile: boolean

  /** Child directories first, then files, each ordered by name; empty for a file. */
  children: PathTreeNode[]

  /** Indexed files at or below this node (1 for a file). */
  files: number

  /** Chunks of those files in the committed generation. */
  chunks: number

  /** Search appearances of those files. */
  appearances: number

  /** Appearances that scored at or above the threshold. */
  hits: number

  /** Appearances below the threshold. */
  misses: number
}

/** A path row with its remaining path segments, while the tree is being built. */
interface PathEntry {
  /** The row. */
  row: PathStat

  /** Segments of the row's path below the level being built. */
  segments: string[]
}

/** Builds the indexed-paths tree from the flat `getPaths` rows. */
export namespace PathTree {
  /** Separator of project-relative paths (the service always writes POSIX paths). */
  export const Separator = "/"

  /**
   * Build the tree: one node per directory and file, each directory summing the analytics of
   * every file below it.
   *
   * @param rows the `getPaths` rows (any order).
   * @returns the top-level nodes.
   */
  export function build(rows: PathStat[]): PathTreeNode[] {
    return buildLevel(
      rows.map(row => ({ row, segments: row.path.split(Separator) })),
      ""
    )
  }

  /**
   * Every directory path of a tree (for "expand all").
   *
   * @param nodes the nodes to walk.
   * @returns directory paths, parents before children.
   */
  export function listDirectoryPaths(nodes: PathTreeNode[]): string[] {
    return nodes
      .filter(({ isFile }) => !isFile)
      .flatMap(({ path, children }) => [path, ...listDirectoryPaths(children)])
  }

  /**
   * The nodes of one level.
   *
   * @param entries the rows below this level.
   * @param prefix the level's path ("" at the top).
   * @returns directories, then files, each ordered by name.
   */
  function buildLevel(entries: PathEntry[], prefix: string): PathTreeNode[] {
    const joinPath = (name: string) =>
        prefix.length === 0 ? name : `${prefix}${Separator}${name}`,
      files = entries
        .filter(({ segments }) => segments.length === 1)
        .map(({ row, segments: [name] }) => newFileNode(row, name)),
      directories = Object.entries(
        groupBy(
          entries.filter(({ segments }) => segments.length > 1),
          ({ segments: [name] }) => name
        )
      ).map(([name, group]) =>
        newDirectoryNode(
          joinPath(name),
          name,
          buildLevel(
            group.map(({ row, segments }) => ({
              row,
              segments: segments.slice(1)
            })),
            joinPath(name)
          )
        )
      )
    return [
      ...sortBy(directories, ({ name }) => name),
      ...sortBy(files, ({ name }) => name)
    ]
  }

  /**
   * A file node.
   *
   * @param row the file's row.
   * @param name its last path segment.
   * @returns the leaf.
   */
  function newFileNode(
    { path, chunks = 0, appearances, hits, misses }: PathStat,
    name: string
  ): PathTreeNode {
    return {
      path,
      name,
      isFile: true,
      children: [],
      files: 1,
      chunks,
      appearances,
      hits,
      misses
    }
  }

  /**
   * A directory node summing its children.
   *
   * @param path the directory's path.
   * @param name its last path segment.
   * @param children its child nodes.
   * @returns the directory.
   */
  function newDirectoryNode(
    path: string,
    name: string,
    children: PathTreeNode[]
  ): PathTreeNode {
    return {
      path,
      name,
      isFile: false,
      children,
      files: sumBy(children, ({ files }) => files),
      chunks: sumBy(children, ({ chunks }) => chunks),
      appearances: sumBy(children, ({ appearances }) => appearances),
      hits: sumBy(children, ({ hits }) => hits),
      misses: sumBy(children, ({ misses }) => misses)
    }
  }
}
