import { ThemeProvider } from "@mui/material/styles"
import {
  render as renderElement,
  renderHook as renderHookElement,
  type RenderHookResult,
  type RenderResult
} from "@testing-library/react"
import { Provider } from "react-redux"
import { MemoryRouter, createMemoryRouter, type DataRouter } from "react-router"
import { RouterProvider } from "react-router/dom"

import {
  AppRouter,
  createCodeSearchStore,
  createCodeSearchTheme,
  type CodeSearchServices,
  type CodeSearchStore
} from "@code-search-local/code-search-local-webapp"

import { FakeServices, type FakeServicesOptions } from "./FakeServices.js"

/** Where {@link RenderWithStore.render} starts the router. */
export interface RenderWithStoreOptions {
  /** The initial path of the in-memory router. */
  path?: string
}

/** What {@link RenderWithStore.render} returns. */
export interface RenderWithStoreResult extends RenderResult {
  /** The store the element was rendered against. */
  store: CodeSearchStore
}

/** What {@link RenderWithStore.renderHook} returns. */
export interface RenderHookWithStoreResult<T> extends RenderHookResult<
  T,
  unknown
> {
  /** The store the hook ran against. */
  store: CodeSearchStore
}

/** Render helpers that wrap an element in the app's store, theme and an in-memory router. */
export namespace RenderWithStore {
  /** Path every in-memory router starts at unless a test names another. */
  export const DefaultPath = "/"

  /**
   * Render `element` inside `Provider` + `ThemeProvider` + `MemoryRouter`. The providers are
   * the render's `wrapper`, so `rerender(next)` keeps the same store, theme and router.
   *
   * @param element the element under test.
   * @param services the services the store runs against.
   * @param options where the router starts.
   * @returns the render result plus the store.
   */
  export function render(
    element: React.ReactElement,
    services: CodeSearchServices,
    { path = DefaultPath }: RenderWithStoreOptions = {}
  ): RenderWithStoreResult {
    const store = createCodeSearchStore(services),
      theme = createCodeSearchTheme(),
      result = renderElement(element, {
        wrapper: ({ children }: React.PropsWithChildren) => (
          <Provider store={store}>
            <ThemeProvider theme={theme}>
              <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
            </ThemeProvider>
          </Provider>
        )
      })
    return { ...result, store }
  }

  /**
   * Run `hook` in a component inside `Provider` (the hook may dispatch and select); the store
   * stays the same across `rerender` and `unmount`.
   *
   * @param hook the hook under test.
   * @param services the services the store runs against.
   * @returns the hook's render result plus the store.
   */
  export function renderHook<T>(
    hook: () => T,
    services: CodeSearchServices
  ): RenderHookWithStoreResult<T> {
    const store = createCodeSearchStore(services),
      result = renderHookElement(hook, {
        wrapper: ({ children }: React.PropsWithChildren) => (
          <Provider store={store}>{children}</Provider>
        )
      })
    return { ...result, store }
  }

  /**
   * An in-memory data router over the app's real route table, started at `path`.
   *
   * @param path the initial path, relative to the basename (the memory router has none).
   * @returns the router to hand `App`.
   */
  export function newMemoryRouter(path = DefaultPath): DataRouter {
    return createMemoryRouter(AppRouter.createRoutes(), {
      initialEntries: [path]
    })
  }

  /**
   * Render the app's real route table at `path` inside `Provider` + `ThemeProvider` (what `App`
   * renders, with a memory router).
   *
   * @param services the services the store runs against.
   * @param path the initial path.
   * @returns the render result plus the store.
   */
  export function renderRoutes(
    services: CodeSearchServices,
    path = DefaultPath
  ): RenderWithStoreResult {
    const store = createCodeSearchStore(services),
      result = renderElement(
        <Provider store={store}>
          <ThemeProvider theme={createCodeSearchTheme()}>
            <RouterProvider router={newMemoryRouter(path)} />
          </ThemeProvider>
        </Provider>
      )
    return { ...result, store }
  }

  /**
   * Services backed by a fake fetch and an in-memory session storage.
   *
   * @param fetchFn the fake's fetch.
   * @param options the origin and the session's token.
   * @returns the services.
   */
  export function newServices(
    fetchFn: typeof fetch,
    options: FakeServicesOptions = {}
  ): CodeSearchServices {
    return FakeServices.create(fetchFn, options)
  }
}
