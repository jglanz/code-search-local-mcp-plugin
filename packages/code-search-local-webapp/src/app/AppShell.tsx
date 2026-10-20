import AppBar from "@mui/material/AppBar"
import Box from "@mui/material/Box"
import Container from "@mui/material/Container"
import Link from "@mui/material/Link"
import Toolbar from "@mui/material/Toolbar"
import Typography from "@mui/material/Typography"
import { Outlet, Link as RouterLink } from "react-router"

import { AuthGate } from "../auth/AuthGate.js"
import { AppRoutePaths } from "../routes/AppRoutePaths.js"
import { AppTitle } from "./AppTitle.js"

/**
 * The app chrome: the title (back to the overview) above the page for the current path, which
 * the router renders into the `Outlet` once a service token is known (the connect screen
 * otherwise). Rendered by a data router (`AppRouter`) inside the store's `Provider`.
 *
 * @returns the shell.
 */
export function AppShell(): React.ReactElement {
  return (
    <Box sx={{ minHeight: "100vh" }}>
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar>
          <Typography variant="h6" component="h1" sx={{ flexGrow: 1 }}>
            <Link
              component={RouterLink}
              to={AppRoutePaths.Overview}
              color="inherit"
              underline="none"
            >
              {AppTitle.Name}
            </Link>
          </Typography>
        </Toolbar>
      </AppBar>
      <Container component="main" maxWidth="xl" sx={{ py: 3 }}>
        <AuthGate>
          <Outlet />
        </AuthGate>
      </Container>
    </Box>
  )
}
