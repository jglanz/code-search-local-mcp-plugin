import { readFileSync } from "node:fs"
import path from "node:path"

import { describe, expect, it } from "@jest/globals"

import { AppTitle } from "@code-search-local/code-search-local-webapp"

/** The page template whose `<title>` shows until a page sets its own. */
const IndexHtmlPath = path.join(
  import.meta.dirname,
  "..",
  "..",
  "resources",
  "index.html"
)

/** The `<title>` element's text (group 1). */
const TitlePattern = /<title>([^<]*)<\/title>/

/** A page name. */
const PageName = "Overview"

describe("AppTitle", () => {
  it("is the title of resources/index.html", () => {
    const [, title] = readFileSync(IndexHtmlPath, "utf8").match(TitlePattern)
    expect(title).toBe(AppTitle.Name)
  })

  it("puts the page name before the app name", () => {
    expect(AppTitle.of(PageName)).toBe(
      `${PageName}${AppTitle.Separator}${AppTitle.Name}`
    )
    expect(AppTitle.of(PageName).startsWith(AppTitle.Name)).toBe(false)
  })
})
