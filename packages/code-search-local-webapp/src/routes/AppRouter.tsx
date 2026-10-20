import { lazy, Suspense } from "react"
import {
  createBrowserRouter,
  type DataRouter,
  type RouteObject
} from "react-router"

import { AppShell } from "../app/AppShell.js"
import { ViewState } from "../dashboard/ViewState.js"
import { ViewStateKind } from "../dashboard/ViewStateKind.js"
import { AppRoutePaths } from "./AppRoutePaths.js"
import { NotFoundPage } from "./NotFoundPage.js"
import { OverviewPage } from "./OverviewPage.js"

/** The project page, loaded as its own chunk on first visit (it carries the tree view). */
const LazyProjectPage = lazy(() =>
  import("./ProjectPage.js").then(module => ({ default: module.ProjectPage }))
)

/** The app's data router: its route table and the browser router built from it. */
export namespace AppRouter {
  /** Test id scope of the page-chunk loading state. */
  export const PageLoadingScope = "page"

  /** Shown while a page chunk loads. */
  export const PageLoadingMessage = "Loading page…"

  /**
   * Every route: the shell around the overview, the project page and the not-found fallback.
   * Tests build a memory router from the same table, so they render exactly the routes the
   * browser does.
   *
   * @returns the route table.
   */
  export function createRoutes(): RouteObject[] {
    return [
      {
        element: <AppShell />,
        children: [
          { path: AppRoutePaths.Overview, element: <OverviewPage /> },
          {
            path: AppRoutePaths.Project,
            element: (
              <Suspense
                fallback={
                  <ViewState
                    kind={ViewStateKind.loading}
                    scope={PageLoadingScope}
                    message={PageLoadingMessage}
                  />
                }
              >
                <LazyProjectPage />
              </Suspense>
            )
          },
          { path: AppRoutePaths.Fallback, element: <NotFoundPage /> }
        ]
      }
    ]
  }

  /**
   * The browser router: history-backed, every path relative to {@link AppRoutePaths.Basename}.
   *
   * @returns the router `RouterProvider` renders.
   */
  export function createBrowser(): DataRouter {
    return createBrowserRouter(createRoutes(), {
      basename: AppRoutePaths.Basename
    })
  }
}
