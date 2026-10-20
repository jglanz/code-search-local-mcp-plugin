/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { fireEvent, screen } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  PathTree,
  PathTreeView
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** The fixture's top-level directory and its child. */
const SrcPath = "src"

/** The nested directory under {@link SrcPath}. */
const AppPath = "src/app"

/** Render the tree of the fixture paths. */
function renderTree(): void {
  RenderWithStore.render(
    <PathTreeView paths={ApiFixtures.Paths.paths} />,
    RenderWithStore.newServices(FakeFetch.create({}).fetch)
  )
}

/**
 * One tree item.
 *
 * @param path its path.
 * @returns the item element.
 */
function itemOf(path: string): HTMLElement {
  return screen.getByTestId(PathTreeView.itemTestIdOf(path))
}

describe("PathTreeView", () => {
  it("starts with top-level directories expanded, showing their summed figures", () => {
    renderTree()
    const [src] = PathTree.build(ApiFixtures.Paths.paths)
    expect(
      screen.getByRole("tree", { name: PathTreeView.Label })
    ).toBeInTheDocument()
    expect(itemOf(SrcPath)).toHaveAttribute("aria-expanded", "true")
    expect(itemOf(SrcPath)).toHaveTextContent(PathTreeView.summaryOf(src))
    expect(itemOf(AppPath)).toHaveAttribute("aria-expanded", "false")
    expect(
      screen.queryByTestId(PathTreeView.itemTestIdOf(ApiFixtures.MainPath.path))
    ).not.toBeInTheDocument()
  })

  it("expands a directory on click, and everything or nothing with the buttons", () => {
    renderTree()
    fireEvent.click(screen.getByText("app"))
    expect(itemOf(AppPath)).toHaveAttribute("aria-expanded", "true")
    expect(itemOf(ApiFixtures.MainPath.path)).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole("button", { name: PathTreeView.CollapseAllLabel })
    )
    expect(itemOf(SrcPath)).toHaveAttribute("aria-expanded", "false")
    fireEvent.click(
      screen.getByRole("button", { name: PathTreeView.ExpandAllLabel })
    )
    expect(itemOf(ApiFixtures.UtilPath.path)).toBeInTheDocument()
  })
})

describe("PathTreeView.summaryOf", () => {
  it("counts a directory's files before its figures", () => {
    const [src] = PathTree.build(ApiFixtures.Paths.paths)
    expect(PathTreeView.summaryOf(src)).toBe(
      "Files 2 · Appearances 4 · Hits 2 · Misses 2"
    )
  })

  it("leaves the file count out for a file", () => {
    const [, readme] = PathTree.build(ApiFixtures.Paths.paths)
    expect(PathTreeView.summaryOf(readme)).toBe(
      "Appearances 0 · Hits 0 · Misses 0"
    )
  })
})
