import { createRoot } from "react-dom/client"

import { App } from "./app/App.js"
import { AppRouter } from "./routes/AppRouter.js"
import { CodeSearchServices } from "./services/CodeSearchServices.js"
import { assertDefined } from "./util/assertUtils.js"

/** Id of the mount element in resources/index.html; both must change together. */
const RootElementId = "root"

const services = CodeSearchServices.createBrowserServices()

// The token arrives once in the fragment (`code-search-local web` opens `/ui/#token=…`); it is
// stored for the session and removed from the address bar before the app first renders.
services.tokenStore.captureFragment(window.location, window.history)

createRoot(
  assertDefined(
    document.getElementById(RootElementId),
    `no #${RootElementId} element in index.html`
  )
).render(<App services={services} router={AppRouter.createBrowser()} />)
