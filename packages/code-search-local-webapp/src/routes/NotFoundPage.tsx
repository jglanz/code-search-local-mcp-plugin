import Alert from "@mui/material/Alert"
import Button from "@mui/material/Button"
import Stack from "@mui/material/Stack"
import { Link } from "react-router"

import { AppRoutePaths } from "./AppRoutePaths.js"

/** Props of {@link NotFoundPage}. */
export interface NotFoundPageProps {
  /** What was not found; a generic message when absent. */
  message?: string
}

/**
 * Shown for an unknown path, with a way back to the overview.
 *
 * @param props the page props.
 * @returns the page.
 */
export function NotFoundPage({
  message = NotFoundPage.DefaultMessage
}: NotFoundPageProps): React.ReactElement {
  return (
    <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
      <Alert severity="warning" data-testid={NotFoundPage.TestId}>
        {message}
      </Alert>
      <Button component={Link} to={AppRoutePaths.Overview}>
        {NotFoundPage.BackLabel}
      </Button>
    </Stack>
  )
}

/** Companion constants for {@link NotFoundPage}. */
export namespace NotFoundPage {
  /** Message for an unknown path. */
  export const DefaultMessage = "There is no page at this address."

  /** Label of the link back to the overview. */
  export const BackLabel = "Back to the overview"

  /** Test id of the message. */
  export const TestId = "not-found"
}
