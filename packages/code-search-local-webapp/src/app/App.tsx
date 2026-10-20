import CssBaseline from "@mui/material/CssBaseline"
import { ThemeProvider } from "@mui/material/styles"
import { useState } from "react"
import { Provider } from "react-redux"
import type { DataRouter } from "react-router"
import { RouterProvider } from "react-router/dom"

import type { CodeSearchServices } from "../services/CodeSearchServices.js"
import { createCodeSearchStore } from "../store/createCodeSearchStore.js"
import { createCodeSearchTheme } from "../theme/createCodeSearchTheme.js"

/** Props of {@link App}. */
export interface AppProps {
  /** Environment the store runs against (browser services in production, fakes in tests). */
  services: CodeSearchServices

  /** The data router (`AppRouter.createBrowser()` in production, a memory router in tests). */
  router: DataRouter
}

/**
 * The app root: store → theme → baseline → router.
 *
 * @param props the app props.
 * @returns the app.
 */
export function App({ services, router }: AppProps): React.ReactElement {
  const [store] = useState(() => createCodeSearchStore(services)),
    [theme] = useState(createCodeSearchTheme)
  return (
    <Provider store={store}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <RouterProvider router={router} />
      </ThemeProvider>
    </Provider>
  )
}
