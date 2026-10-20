import { expect, test, type Page } from "@playwright/test"

import { readE2eService } from "../../etc/playwright/E2eEnvironment.js"

// Black-box checks of the built dashboard served by the real Python daemon (fake model). Test
// ids and user-visible text are spelled out here rather than imported from the app's source,
// which would pull React into the test runner.

/** Where the service serves the dashboard. */
const WebUiPath = "/ui/"

/** The fragment parameter `code-search-local web` hands the token over in. */
const TokenFragmentKey = "token"

/** A token the service never issued. */
const WrongToken = "not-the-service-token"

/** Test id of the connect screen. */
const ConnectScreenTestId = "connect-screen"

/** Test id of the rejected-token alert. */
const RejectedTestId = "connect-rejected"

/** Test id of the service header and its online chip. */
const ServiceHeaderTestId = "service-header"

/** Test id of the online/offline chip. */
const ServiceStatusTestId = "service-status"

/** Chip text of a live service. */
const OnlineLabel = "Online"

/** Test id of the totals' non-empty-results meter. */
const TotalsResultsMeterTestId = "hit-miss-totals-results"

/** Test id of the project's relevance meter. */
const ProjectRelevanceMeterTestId = "hit-miss-project-relevance"

/** Test id of a meter's rate figure. */
const RateTestId = "hit-miss-rate"

/** Test id of the project page. */
const ProjectPageTestId = "project-page"

/** Test id of the indexed-paths tree. */
const PathTreeTestId = "path-tree"

/** Test id of the indexed-paths table section. */
const PathTableTestId = "path-table"

/** A rate as the dashboard formats it, e.g. `100.0%`. */
const RatePattern = /^\d{1,3}\.\d%$/

/** Label of the token field on the connect screen. */
const TokenFieldLabel = "Access token"

/** Label of the connect button. */
const ConnectLabel = "Connect"

/** A top-level directory of the fixture project. */
const FixtureDirectory = "app"

/** The nested directory holding the searched file. */
const FixtureNestedDirectory = "app/util"

/** The last segment of {@link FixtureNestedDirectory}, as the tree labels it. */
const FixtureNestedDirectoryName = "util"

/** The file the fixture search is about. */
const FixtureFile = "app/util/numbers.py"

/** Every indexed fixture file (the table's count line). */
const FixtureFileCount = 4

/**
 * The test id of one project's row in the projects table.
 *
 * @param projectId the project id.
 * @returns the row's test id.
 */
function projectRowTestId(projectId: string): string {
  return `projects-row-${projectId}`
}

/**
 * The test id of one item of the indexed-paths tree.
 *
 * @param itemPath the item's project-relative path.
 * @returns the item's test id.
 */
function treeItemTestId(itemPath: string): string {
  return `path-tree-item-${itemPath}`
}

/**
 * Open the dashboard the way `code-search-local web` does: the token in the fragment.
 *
 * @param page the page.
 * @param token the token to hand over.
 */
async function openWithToken(page: Page, token: string): Promise<void> {
  const { serviceUrl } = readE2eService()
  await page.goto(`${serviceUrl}${WebUiPath}#${TokenFragmentKey}=${token}`)
}

test.describe("dashboard", () => {
  test("takes the token from the fragment and shows the project with its hit rates", async ({
    page
  }) => {
    const { token, projectPath, projectId } = readE2eService()
    await openWithToken(page, token)
    await expect(page.getByTestId(ServiceHeaderTestId)).toBeVisible()
    expect(new URL(page.url()).hash).toBe("")
    await expect(page.getByTestId(ServiceStatusTestId)).toHaveText(OnlineLabel)
    await expect(page.getByTestId(projectRowTestId(projectId))).toContainText(
      projectPath
    )
    await expect(
      page.getByTestId(TotalsResultsMeterTestId).getByTestId(RateTestId)
    ).toHaveText(RatePattern)
  })

  test("opens the project page with its rates, indexed-path tree and file table", async ({
    page
  }) => {
    const { token, projectPath, projectId } = readE2eService()
    await openWithToken(page, token)
    await page.getByTestId(projectRowTestId(projectId)).click()
    await expect(page.getByTestId(ProjectPageTestId)).toBeVisible()
    await expect(
      page.getByRole("heading", { level: 1, name: projectPath })
    ).toBeVisible()
    await expect(
      page.getByTestId(ProjectRelevanceMeterTestId).getByTestId(RateTestId)
    ).toHaveText(RatePattern)
    const tree = page.getByTestId(PathTreeTestId)
    await expect(
      tree.getByTestId(treeItemTestId(FixtureDirectory))
    ).toBeVisible()
    await tree.getByText(FixtureNestedDirectoryName, { exact: true }).click()
    await expect(
      tree.getByTestId(treeItemTestId(FixtureNestedDirectory))
    ).toHaveAttribute("aria-expanded", "true")
    await expect(tree.getByTestId(treeItemTestId(FixtureFile))).toBeVisible()
    const table = page.getByTestId(PathTableTestId)
    await expect(table.getByRole("cell", { name: FixtureFile })).toBeVisible()
    await expect(table).toContainText(
      `${FixtureFileCount} of ${FixtureFileCount}`
    )
  })

  test("asks for a token when none was handed over, and connects with a pasted one", async ({
    page
  }) => {
    const { serviceUrl, token, projectId } = readE2eService()
    await page.goto(`${serviceUrl}${WebUiPath}`)
    await expect(page.getByTestId(ConnectScreenTestId)).toBeVisible()
    await page.getByLabel(TokenFieldLabel).fill(token)
    await page.getByRole("button", { name: ConnectLabel }).click()
    await expect(page.getByTestId(projectRowTestId(projectId))).toBeVisible()
  })

  test("returns to the connect screen when the service rejects the token", async ({
    page
  }) => {
    await openWithToken(page, WrongToken)
    await expect(page.getByTestId(RejectedTestId)).toBeVisible()
    await expect(page.getByTestId(ConnectScreenTestId)).toBeVisible()
  })
})
