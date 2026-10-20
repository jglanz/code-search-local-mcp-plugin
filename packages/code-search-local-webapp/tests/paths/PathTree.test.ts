import { describe, expect, it } from "@jest/globals"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import { PathTree } from "@code-search-local/code-search-local-webapp"

/** The fixture's top-level directory. */
const SrcPath = "src"

/** Its only child directory. */
const AppPath = "src/app"

/** The nested directory below it. */
const UtilPath = "src/app/util"

describe("PathTree.build", () => {
  it("nests files under their directories, directories first, each by name", () => {
    const [src, readme] = PathTree.build(ApiFixtures.Paths.paths),
      [app] = src.children,
      [util, main] = app.children
    expect([src.path, readme.path]).toEqual([
      SrcPath,
      ApiFixtures.ReadmePath.path
    ])
    expect(readme.isFile).toBe(true)
    expect(app.path).toBe(AppPath)
    expect([util.path, util.isFile]).toEqual([UtilPath, false])
    expect([main.path, main.isFile]).toEqual([ApiFixtures.MainPath.path, true])
    expect(util.children.map(({ path }) => path)).toEqual([
      ApiFixtures.UtilPath.path
    ])
  })

  it("sums every file's analytics up the hierarchy", () => {
    const [src] = PathTree.build(ApiFixtures.Paths.paths),
      { MainPath, UtilPath: Util } = ApiFixtures
    expect(src).toMatchObject({
      files: 2,
      chunks: MainPath.chunks + Util.chunks,
      appearances: MainPath.appearances + Util.appearances,
      hits: MainPath.hits + Util.hits,
      misses: MainPath.misses + Util.misses
    })
  })

  it("builds nothing from no rows and counts a row without chunks as 0", () => {
    expect(PathTree.build([])).toEqual([])
    const [file] = PathTree.build([
      { ...ApiFixtures.MainPath, chunks: undefined }
    ])
    expect(file.chunks).toBe(0)
  })
})

describe("PathTree.listDirectoryPaths", () => {
  it("lists every directory, parents before children", () => {
    expect(
      PathTree.listDirectoryPaths(PathTree.build(ApiFixtures.Paths.paths))
    ).toEqual([SrcPath, AppPath, UtilPath])
  })

  it("lists nothing for files only", () => {
    expect(
      PathTree.listDirectoryPaths(PathTree.build([ApiFixtures.ReadmePath]))
    ).toEqual([])
  })
})
