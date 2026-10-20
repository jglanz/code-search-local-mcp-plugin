import Alert from "@mui/material/Alert"
import Box from "@mui/material/Box"
import Button from "@mui/material/Button"
import Stack from "@mui/material/Stack"
import TextField from "@mui/material/TextField"
import Typography from "@mui/material/Typography"
import { useState } from "react"

import { selectTokenRejected } from "../store/auth/AuthSlice.js"
import { enterToken } from "../store/auth/authThunks.js"
import { useCodeSearchDispatch, useCodeSearchSelector } from "../store/hooks.js"

/**
 * Shown instead of every page while no token is known or after the service rejected one: how to
 * open the dashboard with its token (`code-search-local web`), and a field to paste the token.
 *
 * @returns the screen.
 */
export function ConnectScreen(): React.ReactElement {
  const dispatch = useCodeSearchDispatch(),
    rejected = useCodeSearchSelector(selectTokenRejected),
    [token, setToken] = useState(""),
    entered = token.trim()
  return (
    <Stack
      component="section"
      spacing={2}
      aria-label={ConnectScreen.Title}
      data-testid={ConnectScreen.TestId}
      sx={{ maxWidth: ConnectScreen.MaxWidthPx }}
    >
      <Typography variant="h5" component="h2">
        {ConnectScreen.Title}
      </Typography>
      {rejected ? (
        <Alert severity="error" data-testid={ConnectScreen.RejectedTestId}>
          {ConnectScreen.RejectedMessage}
        </Alert>
      ) : null}
      <Typography>
        {ConnectScreen.CommandIntro}{" "}
        <Box component="code" sx={{ fontFamily: "monospace" }}>
          {ConnectScreen.WebCommand}
        </Box>{" "}
        {ConnectScreen.CommandOutcome}
      </Typography>
      <Typography color="text.secondary">{ConnectScreen.PasteHint}</Typography>
      <Stack
        component="form"
        direction="row"
        spacing={1.5}
        sx={{ alignItems: "flex-start" }}
        onSubmit={event => {
          event.preventDefault()
          if (entered.length > 0) dispatch(enterToken(entered))
        }}
      >
        <TextField
          size="small"
          type="password"
          autoComplete="off"
          label={ConnectScreen.TokenLabel}
          value={token}
          onChange={event => setToken(event.target.value)}
          sx={{ flexGrow: 1 }}
        />
        <Button
          type="submit"
          variant="contained"
          disabled={entered.length === 0}
        >
          {ConnectScreen.ConnectLabel}
        </Button>
      </Stack>
    </Stack>
  )
}

/** Companion constants for {@link ConnectScreen}. */
export namespace ConnectScreen {
  /** The screen's heading. */
  export const Title = "Connect to the Code Search Local service"

  /** Test id of the screen. */
  export const TestId = "connect-screen"

  /** Test id of the rejected-token alert. */
  export const RejectedTestId = "connect-rejected"

  /**
   * The CLI command that prints and opens the dashboard URL carrying the token; it must stay the
   * service CLI's command name.
   */
  export const WebCommand = "code-search-local web"

  /** Before the command. */
  export const CommandIntro = "Run"

  /** After the command. */
  export const CommandOutcome =
    "in a terminal: it opens this dashboard with the service's access token."

  /** How to connect without the command. */
  export const PasteHint =
    "Or paste the token here: the token value of auth.json in the service storage directory."

  /** Shown after the service answered 401. */
  export const RejectedMessage =
    "The service rejected the access token. Connect again with a current token."

  /** Label of the token field. */
  export const TokenLabel = "Access token"

  /** Label of the submit button. */
  export const ConnectLabel = "Connect"

  /** Widest the screen grows, in px. */
  export const MaxWidthPx = 720
}
